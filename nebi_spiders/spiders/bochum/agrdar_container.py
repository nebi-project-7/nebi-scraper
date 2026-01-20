"""
Agrdar Container Spider
Extrahiert Preise für Container-Entsorgung in Bochum
Website: https://www.agrdar-container.de/
"""

import re
import logging
from time import sleep

from scrapy import Spider

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager


class AgrdarContainerSpider(Spider):
    name = "agrdar-container"
    allowed_domains = ["agrdar-container.de"]
    start_urls = ["https://www.agrdar-container.de/"]

    # Abfallarten mit URLs
    WASTE_PAGES = [
        ("https://www.agrdar-container.de/container-fuer-bauschutt", "Bauschutt"),
        ("https://www.agrdar-container.de/container-fuer-baumisch", "Baumischabfall"),
        ("https://www.agrdar-container.de/container-fuer-holz-aii", "Holz A1-A3"),
        ("https://www.agrdar-container.de/container-fuer-holz-aiv", "Holz A4"),
        ("https://www.agrdar-container.de/container-fuer-gips", "Gips"),
        ("https://www.agrdar-container.de/container-fuer-gruenabfaelle", "Gartenabfälle"),
        ("https://www.agrdar-container.de/container-fuer-sperrmuell", "Sperrmüll"),
        ("https://www.agrdar-container.de/container-fuer-boden-steine", "Boden/Steine"),
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
        self.log(f"Starte Agrdar Container Scraping für Bochum")
        self.log(f"{'='*80}\n")

        total_products = 0

        try:
            for url, waste_type in self.WASTE_PAGES:
                self.log(f"\n--- {waste_type} ---")

                self.driver.get(url)
                sleep(2)

                # Suche nach Tabelle mit Preisen
                tables = self.driver.find_elements(By.TAG_NAME, "table")

                for table in tables:
                    rows = table.find_elements(By.TAG_NAME, "tr")

                    for row in rows:
                        text = row.text.strip()

                        if '€' in text and 'm³' in text:
                            # Extrahiere Größe und Preis
                            size_match = re.search(r'(\d+)\s*m³', text)
                            price_match = re.search(r'ab\s*([\d.,]+)\s*€', text)

                            if size_match and price_match:
                                size = f"{size_match.group(1)} m³"
                                price_raw = price_match.group(1)

                                # Überspringe 0,00 € Preise
                                if price_raw == "0,00":
                                    continue

                                # Preis formatieren (Punkt als Tausendertrennzeichen entfernen)
                                price = f"ab {price_raw.replace('.', '')}"

                                product = {
                                    "source": "Agrdar Container",
                                    "title": f"{size} {waste_type}",
                                    "type": waste_type,
                                    "city": "Bochum",
                                    "size": size,
                                    "price": price,
                                    "lid_price": "auf Anfrage",
                                    "arrival_price": "inklusive",
                                    "departure_price": "inklusive",
                                    "max_rental_period": "14 Tage",
                                    "fee_after_max": "1,26 EUR/Tag",
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
