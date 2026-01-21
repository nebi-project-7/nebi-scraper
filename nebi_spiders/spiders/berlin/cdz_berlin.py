"""
CDZ Berlin Spider (Containerdienst Zieske GmbH)
Extrahiert Preise für Container-Entsorgung in Berlin
Website: https://cdz-berlin.de/online-shop/
"""

import re
import logging
from time import sleep

from scrapy import Spider

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager


class CdzBerlinSpider(Spider):
    name = "cdz-berlin"
    allowed_domains = ["cdz-berlin.de"]
    start_urls = ["https://cdz-berlin.de/online-shop/"]

    # Produkt-Seiten mit Abfallarten
    PRODUCT_PAGES = [
        ("https://cdz-berlin.de/produkt/bauschutt/", "Bauschutt"),
        ("https://cdz-berlin.de/produkt/baumischabfall-siedlungsabfaelle/", "Baumischabfall"),
        ("https://cdz-berlin.de/produkt/beton-ohne-stahl/", "Beton"),
        ("https://cdz-berlin.de/produkt/beton-mit-stahl/", "Beton bewehrt"),
        ("https://cdz-berlin.de/produkt/sperrmuell/", "Sperrmüll"),
        ("https://cdz-berlin.de/produkt/holzabfaelle/", "Holz A1-A3"),
        ("https://cdz-berlin.de/produkt/gartenabfaelle-max-bis-15cm-o/", "Gartenabfälle"),
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

    def parse(self, response):
        self.log(f"\n{'='*80}")
        self.log(f"Starte CDZ Berlin Scraping")
        self.log(f"{'='*80}\n")

        total_products = 0

        try:
            self._init_driver()

            for url, waste_type in self.PRODUCT_PAGES:
                self.log(f"\n--- {waste_type} ---")

                self.driver.get(url)
                sleep(2)

                body_text = self.driver.find_element(By.TAG_NAME, "body").text
                lines = body_text.split('\n')

                for i, line in enumerate(lines):
                    line = line.strip()

                    # Suche nach Container-Zeilen (z.B. "Container 3m³")
                    if re.match(r'Container \d+m³', line):
                        size_match = re.search(r'(\d+)m³', line)
                        if size_match:
                            size = size_match.group(1)

                            # Preis ist in nächster Zeile
                            if i + 1 < len(lines):
                                price_line = lines[i + 1].strip()
                                price_match = re.search(r'([\d.,]+)\s*€', price_line)
                                if price_match:
                                    price = price_match.group(1)

                                    # Container-Typ basierend auf Größe
                                    if int(size) <= 12:
                                        container_type = "Absetzcontainer"
                                    else:
                                        container_type = "Abrollcontainer"

                                    product = {
                                        "source": "CDZ Berlin",
                                        "title": f"{size} m³ {waste_type} ({container_type})",
                                        "type": waste_type,
                                        "city": "Berlin",
                                        "size": f"{size} m³",
                                        "price": price,
                                        "lid_price": "auf Anfrage",
                                        "arrival_price": "inklusive",
                                        "departure_price": "inklusive",
                                        "max_rental_period": "14 Tage",
                                        "fee_after_max": "auf Anfrage",
                                        "cancellation_fee": None,
                                        "URL": url
                                    }

                                    total_products += 1
                                    self.log(f"  ✓ {size} m³: {price} €")
                                    yield product

        except Exception as e:
            self.log(f"FEHLER: {e}")
            import traceback
            self.log(traceback.format_exc())

        self.log(f"\n{'='*80}")
        self.log(f"Gesamt gescrapt: {total_products} Produkte")
        self.log(f"{'='*80}\n")
