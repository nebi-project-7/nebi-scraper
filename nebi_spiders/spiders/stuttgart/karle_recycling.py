"""
Karle Recycling Spider
Extrahiert Preise für Container-Entsorgung in Stuttgart
Website: https://www.karlerecycling.de/

2026-05-17: Umgestellt auf Ninja Forms 3.x (Geolocation Add-on).
  - Alte Selectors (textbox-container, data-key) entfernt
  - Form-Felder via aria-labelledby/Label-Text identifizieren
  - Preis-Extraktion via Value-Pattern (\\d+,\\d{2}€) auf nf-element Inputs
  - WebDriverWait statt sleep, User-Agent gesetzt gegen NinjaFirewall
"""

import logging
import re
from time import sleep
from datetime import datetime

from scrapy import Spider

from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager


PRICE_PATTERN = re.compile(r'^(\d{1,5}[,.]\d{2})\s*€?\s*$')


class KarleRecyclingSpider(Spider):
    name = "karle-recycling"
    allowed_domains = ["karlerecycling.de"]
    start_urls = ["https://www.karlerecycling.de/onlineshop-fuer-privatpersonen-karle-recycling/"]

    # PLZ für Stuttgart
    PLZ = "70193"

    # Container-Größen (Preis ist laut Karle-Form unabhängig von Größe und Deckel)
    CONTAINER_SIZES = ["3 m³", "5 m³", "7 m³", "10 m³"]

    # Abfallarten mit URLs
    WASTE_PAGES = [
        ("https://www.karlerecycling.de/bauschutt/", "Bauschutt"),
        ("https://www.karlerecycling.de/mischabfall/", "Baumischabfall"),
        ("https://www.karlerecycling.de/altholz-ai-aii/", "Holz A1-A3"),
        ("https://www.karlerecycling.de/altholz-a-iv/", "Holz A4"),
        ("https://www.karlerecycling.de/gips/", "Gips"),
    ]

    PLZ_LABEL_HINT = "postleitzahl"
    USER_AGENT = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
    )

    def __init__(self):
        logging.getLogger("selenium").setLevel(logging.WARNING)
        logging.getLogger("urllib3").setLevel(logging.WARNING)
        logging.getLogger("WDM").setLevel(logging.WARNING)

        options = webdriver.ChromeOptions()
        options.add_argument('--headless=new')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.add_argument('--window-size=1920,1080')
        options.add_argument(f'--user-agent={self.USER_AGENT}')
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)

        service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=options)
        # webdriver-Property maskieren (NinjaFirewall-Bypass)
        self.driver.execute_cdp_cmd(
            "Page.addScriptToEvaluateOnNewDocument",
            {"source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"},
        )

    def closed(self, reason):
        try:
            self.driver.quit()
        except Exception:
            pass

    def parse(self, response):
        self.log(f"\n{'='*80}")
        self.log(f"Starte Karle Recycling Scraping für Stuttgart (PLZ: {self.PLZ})")
        self.log(f"{'='*80}\n")

        total_products = 0

        for url, waste_type in self.WASTE_PAGES:
            self.log(f"\n--- {waste_type} ---")

            try:
                price = self._extract_price(url, waste_type)
            except Exception as e:
                self.log(f"  EXCEPTION bei {waste_type}: {type(e).__name__}: {e}")
                self._save_failure_artifacts(waste_type)
                continue

            if not price:
                self.log(f"  FEHLER: Kein Preis gefunden für {waste_type}")
                self._save_failure_artifacts(waste_type)
                continue

            self.log(f"  Preis: {price} EUR")

            for size in self.CONTAINER_SIZES:
                product = {
                    "source": "Karle Recycling",
                    "title": f"{size} {waste_type}",
                    "type": waste_type,
                    "city": "Stuttgart",
                    "size": size,
                    "price": price,
                    "lid_price": "inklusive",
                    "arrival_price": "inklusive",
                    "departure_price": "inklusive",
                    "max_rental_period": "14 Tage",
                    "fee_after_max": None,
                    "cancellation_fee": None,
                    "URL": url,
                }
                total_products += 1
                self.log(f"  ✓ {size}: {price} EUR")
                yield product

        self.log(f"\n{'='*80}")
        self.log(f"Gesamt gescrapt: {total_products} Produkte")
        self.log(f"{'='*80}\n")

        if total_products == 0:
            # Lautes Signal statt stiller Erfolg
            self.logger.error(
                "Karle Recycling Spider hat 0 Produkte extrahiert — "
                "vermutlich Form-Struktur erneut geändert oder NinjaFirewall-Block."
            )

    def _extract_price(self, url, waste_type):
        """Lädt Seite, gibt PLZ ein, liest dynamisch berechneten Brutto-Preis."""
        self.driver.get(url)

        # Block-Check: NinjaFirewall 403
        if "NinjaFirewall" in self.driver.page_source[:1000] or "403 Forbidden" in self.driver.title:
            raise RuntimeError(f"NinjaFirewall blockt Headless-Browser auf {url}")

        # Warte bis Ninja Forms rendert (echte Field-IDs erscheinen)
        try:
            WebDriverWait(self.driver, 20).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "input[id^='nf-field-']"))
            )
        except TimeoutException:
            self.log("  Ninja Forms render-Timeout (20s)")
            return None

        sleep(2)  # Conditional Logic settle

        # PLZ-Feld via Label-Text finden
        plz_input = self._find_plz_field()
        if not plz_input:
            self.log("  PLZ-Feld nicht gefunden")
            return None

        # PLZ eingeben + Trigger
        plz_input.click()
        plz_input.clear()
        plz_input.send_keys(self.PLZ)
        plz_input.send_keys(Keys.TAB)

        # Warte auf Preis-Update (Conditional Logic + Geolocation-Lookup)
        try:
            WebDriverWait(self.driver, 15).until(self._price_field_filled)
        except TimeoutException:
            self.log("  Preis-Update nach PLZ-Eingabe ausgeblieben (15s)")
            return None

        # Preis aus dem aktualisierten Feld lesen
        return self._read_price()

    def _find_plz_field(self):
        """Findet das obere PLZ-Eingabefeld via aria-labelledby → Label-Text 'Postleitzahl'."""
        # Primär: nf-field-Input mit aria-labelledby auf Label, das "postleitzahl" enthält
        # und NICHT die Adress-PLZ ist (diese hat Label "PLZ" — wir wollen "Geben Sie Ihre Postleitzahl ein")
        for inp in self.driver.find_elements(By.CSS_SELECTOR, "input[id^='nf-field-'][type='text']"):
            try:
                lid = inp.get_attribute("aria-labelledby")
                if not lid:
                    continue
                label = self.driver.find_element(By.ID, lid)
                txt = (label.text or "").lower()
                if "geben sie ihre postleitzahl" in txt or "postleitzahl ein" in txt:
                    return inp
            except Exception:
                continue

        # Fallback: XPath via Label-Text
        try:
            return self.driver.find_element(
                By.XPATH,
                "//label[contains(translate(., 'PLZ', 'plz'), 'postleitzahl')]"
                "/ancestor::*[contains(@class,'nf-field-container')][1]"
                "//input[starts-with(@id,'nf-field-')]"
            )
        except Exception:
            return None

    def _price_field_filled(self, driver):
        """Predicate für WebDriverWait: erfüllt sobald ein nf-field-Input einen Brutto-Preis im Format `\\d+,\\d{2}€` hält."""
        for inp in driver.find_elements(By.CSS_SELECTOR, "input[id^='nf-field-']"):
            v = (inp.get_attribute("value") or "").strip()
            if v.endswith("€") and PRICE_PATTERN.match(v):
                return True
        return False

    def _read_price(self):
        """Liest den Brutto-Preis aus dem Ninja-Forms-Input mit €-Suffix."""
        # Bevorzugt: Input mit Value im Format "XXX,XX€" (Brutto)
        for inp in self.driver.find_elements(By.CSS_SELECTOR, "input[id^='nf-field-']"):
            v = (inp.get_attribute("value") or "").strip()
            m = PRICE_PATTERN.match(v)
            if m and v.endswith("€"):
                # Entferne €-Suffix, normalisiere
                return m.group(1)

        # Fallback: pures Preis-Pattern ohne €-Suffix (für Edge-Cases)
        candidates = []
        for inp in self.driver.find_elements(By.CSS_SELECTOR, "input[id^='nf-field-']"):
            v = (inp.get_attribute("value") or "").strip()
            m = PRICE_PATTERN.match(v)
            if m and v != "0,00":
                candidates.append(m.group(1))
        # Größter Wert ist meist Brutto-Total
        if candidates:
            try:
                return max(candidates, key=lambda x: float(x.replace(",", ".")))
            except ValueError:
                return candidates[0]

        return None

    def _save_failure_artifacts(self, waste_type):
        """Screenshot + DOM-Dump für Debug bei Failure."""
        try:
            stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            safe = re.sub(r'[^a-zA-Z0-9_-]', '_', waste_type)
            png = f"/tmp/karle_fail_{safe}_{stamp}.png"
            html = f"/tmp/karle_fail_{safe}_{stamp}.html"
            self.driver.save_screenshot(png)
            with open(html, "w") as f:
                f.write(self.driver.page_source)
            self.log(f"  Debug-Artifacts: {png} / {html}")
        except Exception as e:
            self.log(f"  Konnte Debug-Artifacts nicht speichern: {e}")
