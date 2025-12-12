import logging
import re
from time import sleep

from scrapy import Spider
from scrapy.selector import Selector

from selenium import webdriver
from selenium.webdriver.common.by import By


class KlebsContainerProductsSpider(Spider):
    name = "klebs-container-products"
    allowed_domains = ["klebs.info"]

    # Abfallarten URLs
    waste_type_urls = [
        ("https://www.klebs.info/abfaelle/altholz/", "Altholz"),
        ("https://www.klebs.info/abfaelle/asbest/", "Asbest"),
        ("https://www.klebs.info/abfaelle/baumischabfall/", "Baumischabfall"),
        ("https://www.klebs.info/abfaelle/bauschutt/", "Bauschutt"),
        ("https://www.klebs.info/abfaelle/gipsabfaelle/", "Gipsabfälle"),
        ("https://www.klebs.info/abfaelle/behandeltes-holz/", "Behandeltes Holz"),
        ("https://www.klebs.info/abfaelle/dachpappe/", "Dachpappe"),
        ("https://www.klebs.info/abfaelle/daemmwolle/", "Dämmwolle"),
        ("https://www.klebs.info/abfaelle/gartenabfall/", "Gartenabfall"),
        ("https://www.klebs.info/gewerbeabfall/", "Gewerbeabfall"),
        ("https://www.klebs.info/abfaelle/sperrmuell/", "Sperrmüll"),
    ]

    start_urls = ["https://www.klebs.info/abfaelle/"]

    def __init__(self):
        logging.getLogger("selenium").setLevel(logging.WARNING)
        logging.getLogger("urllib3").setLevel(logging.WARNING)

        options = webdriver.ChromeOptions()
        options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.add_argument('--window-size=1920,1080')
        self.driver = webdriver.Chrome(options=options)

    def closed(self, reason):
        try:
            self.driver.quit()
        except Exception:
            pass

    def parse(self, response):
        self.log(f"\n{'='*80}")
        self.log(f"Starte Klebs Container Scraping")
        self.log(f"{'='*80}\n")

        total_products = 0

        # Für jede Abfallart
        for url, display_name in self.waste_type_urls:
            self.log(f"\n--- Verarbeite: {display_name} ---")

            try:
                # Navigiere zur Abfallart-Seite
                self.driver.get(url)
                sleep(3)

                # Cookie-Banner wegklicken (nur beim ersten Aufruf)
                self._dismiss_cookie_banner()

                # Finde alle Container-Links
                container_links = self._find_container_links()

                if not container_links:
                    self.log(f"  ⚠️ Keine Container-Links gefunden")
                    continue

                self.log(f"  Gefunden: {len(container_links)} Container-Links")

                # Für jeden Container-Link
                for container_url in container_links:
                    try:
                        # Navigiere zur Container-Seite
                        self.driver.get(container_url)
                        sleep(2)

                        # Extrahiere Preis und Größe
                        product = self._extract_product(container_url, display_name)

                        if product:
                            total_products += 1
                            self.log(f"  ✓ {product['size']}m³: {product['price']}€")
                            yield product

                    except Exception as e:
                        self.log(f"  ❌ Fehler bei {container_url}: {e}")
                        continue

            except Exception as e:
                self.log(f"  ❌ Fehler: {e}")
                continue

        self.log(f"\n{'='*80}")
        self.log(f"✓ Gesamt gescrapt: {total_products} Produkte")
        self.log(f"{'='*80}\n")

    def _dismiss_cookie_banner(self):
        """
        Versucht, den Cookie-Banner zu schließen.
        """
        try:
            # Suche nach Cookie-Banner-Buttons
            cookie_buttons = self.driver.find_elements(
                By.XPATH,
                "//button[contains(., 'Akzeptieren') or contains(., 'Accept') or contains(., 'OK') or contains(@class, 'cookie') or contains(@id, 'cookie')]"
            )

            if cookie_buttons:
                for btn in cookie_buttons:
                    try:
                        if btn.is_displayed():
                            btn.click()
                            self.log("✓ Cookie-Banner geschlossen")
                            sleep(1)
                            return
                    except:
                        pass
        except:
            pass

    def _find_container_links(self):
        """
        Findet alle Container-Links auf der aktuellen Abfallart-Seite.
        """
        container_links = []

        try:
            links = self.driver.find_elements(By.TAG_NAME, "a")

            for link in links:
                href = link.get_attribute("href")

                if href and "/containerdienst/" in href and "-container" in href:
                    container_links.append(href)

            # Entferne Duplikate
            container_links = list(set(container_links))

        except Exception as e:
            self.log(f"Fehler beim Finden der Container-Links: {e}")

        return container_links

    def _extract_product(self, container_url: str, waste_type: str):
        """
        Extrahiert Preis und Größe von einer Container-Seite.
        """
        try:
            visible_text = self.driver.execute_script("return document.body.innerText;")

            # Extrahiere Preis (Mietpreis)
            # Pattern berücksichtigt Tausendertrennzeichen: 1.071,00 € oder 321,30 €
            price = ""
            price_match = re.search(r'Mietpreis.*?(\d{1,3}(?:[.,]\d{3})*[.,]\d{2})\s*€', visible_text, re.DOTALL | re.IGNORECASE)
            if price_match:
                # Normalisiere: 1.071,00 → 1071,00 (behalte Komma als Dezimalzeichen)
                price_str = price_match.group(1)
                # Entferne nur Tausendertrennzeichen (Punkt), behalte Komma
                if '.' in price_str and ',' in price_str:
                    # Format: 1.071,00 → 1071,00
                    price = price_str.replace('.', '')
                else:
                    # Format: 321,30 → bleibt 321,30
                    price = price_str

            # Extrahiere Größe aus Seitentitel (nicht aus URL, da URLs manchmal falsch sind!)
            # Beispiel: "5,5 cbm (Kubikmeter) Gartenabfall – Container"
            size = ""
            page_title = self.driver.title

            # Pattern für Größe im Titel: "5,5 cbm" oder "10 cbm"
            size_match = re.search(r'(\d+)[.,](\d+)\s*(?:cbm|m³|m3|Kubikmeter)', page_title, re.IGNORECASE)
            if size_match:
                # Format: 5,5 → 5.5
                size = f"{size_match.group(1)}.{size_match.group(2)}"
            else:
                # Ganzzahl ohne Dezimalstelle
                size_match = re.search(r'(\d+)\s*(?:cbm|m³|m3|Kubikmeter)', page_title, re.IGNORECASE)
                if size_match:
                    size = size_match.group(1)

            if not size or not price:
                self.log(f"⚠️ Größe oder Preis nicht gefunden für {container_url}")
                return None

            product = {
                "source": "klebs.info",
                "title": f"{size} m³ {waste_type}",
                "type": waste_type,
                "city": "Berlin",
                "size": size,
                "price": price,
                "lid_price": "",
                "arrival_price": "inklusive",
                "departure_price": "inklusive",
                "max_rental_period": "15",
                "fee_after_max": "6,54",
                "cancellation_fee": "",
                "URL": container_url
            }

            return product

        except Exception as e:
            self.log(f"Fehler beim Extrahieren: {e}")
            return None
