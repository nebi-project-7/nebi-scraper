"""
Karle Recycling Spider
Extrahiert Preise für Container-Entsorgung in Stuttgart
Website: https://www.karlerecycling.de/
"""

import logging
import re
from time import sleep

from scrapy import Spider

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager


class KarleRecyclingSpider(Spider):
    name = "karle-recycling"
    allowed_domains = ["karlerecycling.de"]
    start_urls = ["https://www.karlerecycling.de/onlineshop-fuer-privatpersonen-karle-recycling/"]

    # PLZ für Stuttgart
    PLZ = "70193"

    # Container-Größen (Preis ist unabhängig von Größe und Deckel)
    CONTAINER_SIZES = ["3 m³", "5 m³", "7 m³", "10 m³"]

    # Abfallarten mit URLs
    WASTE_PAGES = [
        ("https://www.karlerecycling.de/bauschutt/", "Bauschutt"),
        ("https://www.karlerecycling.de/mischabfall/", "Baumischabfall"),
        ("https://www.karlerecycling.de/altholz-ai-aii/", "Holz A1-A3"),
        ("https://www.karlerecycling.de/altholz-a-iv/", "Holz A4"),
        ("https://www.karlerecycling.de/gips/", "Gips"),
    ]

    def __init__(self):
        logging.getLogger("selenium").setLevel(logging.WARNING)
        logging.getLogger("urllib3").setLevel(logging.WARNING)

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
            self.driver.quit()
        except Exception:
            pass

    def parse(self, response):
        self.log(f"\n{'='*80}")
        self.log(f"Starte Karle Recycling Scraping für Stuttgart (PLZ: {self.PLZ})")
        self.log(f"{'='*80}\n")

        total_products = 0

        try:
            for url, waste_type in self.WASTE_PAGES:
                self.log(f"\n--- {waste_type} ---")

                price = self._extract_price(url)

                if not price:
                    self.log(f"  FEHLER: Kein Preis gefunden für {waste_type}")
                    continue

                self.log(f"  Preis: {price} EUR")

                # Produkt für jede Containergröße erstellen (Preis ist gleich)
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
                        "URL": url
                    }

                    total_products += 1
                    self.log(f"  ✓ {size}: {price} EUR")
                    yield product

        except Exception as e:
            self.log(f"FEHLER: {e}")
            import traceback
            self.log(traceback.format_exc())

        self.log(f"\n{'='*80}")
        self.log(f"Gesamt gescrapt: {total_products} Produkte")
        self.log(f"{'='*80}\n")

    def _extract_price(self, url):
        """Extrahiert den Preis für eine Abfallart nach PLZ-Eingabe."""
        self.driver.get(url)
        sleep(3)

        # Finde PLZ-Feld
        plz_field = self._find_plz_field()
        if not plz_field:
            self.log("  PLZ-Feld nicht gefunden")
            return None

        # PLZ eingeben
        plz_field.clear()
        plz_field.send_keys(self.PLZ)
        plz_field.send_keys(Keys.TAB)
        sleep(2)

        # Preis extrahieren
        try:
            price_elem = self.driver.find_element(By.CSS_SELECTOR, "[data-key='field:zahlenderbetragges']")
            price_text = price_elem.text
            if price_text and price_text != "0,00":
                return price_text
        except:
            pass

        # Alternative: Suche im Body
        try:
            body_text = self.driver.find_element(By.TAG_NAME, "body").text
            for line in body_text.split('\n'):
                if 'Gesamtsumme' in line:
                    match = re.search(r'(\d+[,.]?\d*)', line)
                    if match:
                        return match.group(1)
        except:
            pass

        return None

    def _find_plz_field(self):
        """Findet das PLZ-Eingabefeld."""
        # Suche nach Container mit "Postleitzahl" Label
        try:
            containers = self.driver.find_elements(By.CSS_SELECTOR, "[class*='textbox-container']")
            for cont in containers:
                try:
                    label = cont.find_element(By.TAG_NAME, "label").text
                    if "Postleitzahl" in label:
                        return cont.find_element(By.TAG_NAME, "input")
                except:
                    continue
        except:
            pass

        # Alternative: Suche nach Input mit Postleitzahl
        try:
            return self.driver.find_element(By.XPATH, "//label[contains(text(), 'Postleitzahl')]/following-sibling::div//input")
        except:
            pass

        return None
