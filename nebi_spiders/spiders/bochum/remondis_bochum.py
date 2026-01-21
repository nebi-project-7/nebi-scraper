"""
Remondis Bochum Spider
Extrahiert Preise für Container-Entsorgung in Bochum
Website: https://remondis-shop.de/
"""

import re
import logging
from time import sleep

from scrapy import Spider

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager


class RemondisBochumSpider(Spider):
    name = "remondis-bochum"
    allowed_domains = ["remondis-shop.de"]
    start_urls = ["https://remondis-shop.de/"]

    # PLZ für Bochum
    PLZ = "44787"

    # Abfallarten mit URLs
    WASTE_PAGES = [
        ("bauschutt", "Bauschutt"),
        ("baumischabfaelle", "Baumischabfall"),
        ("garten-und-parkabfaelle", "Gartenabfälle"),
        ("holzabfaelle", "Holz"),
        ("sperrmuell", "Sperrmüll"),
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        logging.getLogger("selenium").setLevel(logging.WARNING)
        logging.getLogger("urllib3").setLevel(logging.WARNING)

        self.driver = None

    def _init_driver(self):
        """Initialisiert den WebDriver"""
        if self.driver is None:
            options = webdriver.ChromeOptions()
            options.add_argument('--headless')
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--disable-gpu')
            options.add_argument('--window-size=1920,1080')

            service = Service(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service, options=options)

    def closed(self, reason):
        try:
            if self.driver:
                self.driver.quit()
        except Exception:
            pass

    def _enter_plz(self):
        """PLZ auf aktueller Seite eingeben"""
        try:
            plz_inputs = self.driver.find_elements(By.CSS_SELECTOR, "input[name='zipSearch']")
            for inp in plz_inputs:
                if inp.is_displayed():
                    inp.clear()
                    inp.send_keys(self.PLZ)
                    sleep(1)
                    try:
                        btn = self.driver.find_element(
                            By.XPATH,
                            "//button[contains(text(), 'Los') or contains(text(), 'Abfallbehälter')]"
                        )
                        btn.click()
                    except Exception:
                        inp.send_keys(Keys.RETURN)
                    sleep(3)
                    return True
        except Exception:
            pass
        return False

    def _accept_cookies(self):
        """Cookie-Banner akzeptieren"""
        try:
            accept_btn = self.driver.find_element(
                By.XPATH,
                "//button[contains(text(), 'Alle zulassen')]"
            )
            accept_btn.click()
            sleep(2)
        except Exception:
            pass

    def parse(self, response):
        self.log(f"\n{'='*80}")
        self.log(f"Starte Remondis Scraping für Bochum (PLZ: {self.PLZ})")
        self.log(f"{'='*80}\n")

        total_products = 0

        try:
            # WebDriver initialisieren
            self._init_driver()

            # Zuerst Hauptseite laden und Cookies akzeptieren
            self.driver.get(self.start_urls[0])
            sleep(3)
            self._accept_cookies()

            for slug, waste_type in self.WASTE_PAGES:
                self.log(f"\n--- {waste_type} ---")

                url = f"https://remondis-shop.de/{slug}/"
                self.driver.get(url)
                sleep(2)

                # PLZ eingeben
                plz_entered = self._enter_plz()
                self.log(f"  PLZ eingegeben: {plz_entered}")

                body_text = self.driver.find_element(By.TAG_NAME, "body").text
                lines = body_text.split('\n')


                for i, line in enumerate(lines):
                    line = line.strip()

                    # Suche nach Produktnamen mit m³ (z.B. "5 m³ Absetzkippermulde (Bauschutt)")
                    if 'm³' in line and '(' in line and ')' in line:
                        # Preis ist 2 Zeilen nach dem Produktnamen
                        if i + 2 < len(lines):
                            price_line = lines[i + 2].strip()
                            if '€' in price_line:
                                # Extrahiere Größe
                                size_match = re.match(r'(\d+)\s*m³', line)
                                if size_match:
                                    size = size_match.group(1)

                                    # Extrahiere Preis (entferne "Ab " und " inkl. MwSt.")
                                    price_match = re.search(r'(?:Ab\s+)?([\d.,]+)\s*€', price_line)
                                    if price_match:
                                        price = price_match.group(1).replace('.', '').replace(',', ',')

                                        # Bestimme Container-Typ
                                        container_type = ""
                                        if "Big Bag" in line:
                                            container_type = "Big Bag"
                                        elif "Abrollkippermulde" in line:
                                            container_type = "Abrollcontainer"
                                        else:
                                            container_type = "Absetzcontainer"

                                        # Preis ist "ab" Preis wenn "Ab" im Text
                                        is_ab_price = "Ab " in price_line

                                        product = {
                                            "source": "Remondis Bochum",
                                            "title": f"{size} m³ {waste_type} ({container_type})",
                                            "type": waste_type,
                                            "city": "Bochum",
                                            "size": f"{size} m³",
                                            "price": f"ab {price}" if is_ab_price else price,
                                            "lid_price": "auf Anfrage",
                                            "arrival_price": "inklusive",
                                            "departure_price": "inklusive",
                                            "max_rental_period": "14 Tage",
                                            "fee_after_max": "auf Anfrage",
                                            "cancellation_fee": None,
                                            "URL": url
                                        }

                                        total_products += 1
                                        self.log(f"  ✓ {size} m³ ({container_type}): {price} EUR")
                                        yield product

        except Exception as e:
            self.log(f"FEHLER: {e}")
            import traceback
            self.log(traceback.format_exc())

        self.log(f"\n{'='*80}")
        self.log(f"Gesamt gescrapt: {total_products} Produkte")
        self.log(f"{'='*80}\n")
