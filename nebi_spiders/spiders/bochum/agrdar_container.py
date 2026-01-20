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

    # Bochum-spezifische URLs mit korrekten Preisen
    WASTE_PAGES = [
        ("https://www.agrdar-container.de/bochum_bauschutt", "Bauschutt"),
        ("https://www.agrdar-container.de/bochum_baumisch", "Baumischabfall"),
        ("https://www.agrdar-container.de/bochum_holz-aii", "Holz A1-A3"),
        ("https://www.agrdar-container.de/bochum_holz-aiv", "Holz A4"),
        ("https://www.agrdar-container.de/bochum_gips", "Gips"),
        ("https://www.agrdar-container.de/bochum_gruenabfaelle", "Gartenabfälle"),
        ("https://www.agrdar-container.de/bochum_sperrmuell", "Sperrmüll"),
        ("https://www.agrdar-container.de/bochum_boden-steine", "Boden/Steine"),
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
                sleep(3)

                body_text = self.driver.find_element(By.TAG_NAME, "body").text
                lines = body_text.split('\n')

                current_size = None

                for i, line in enumerate(lines):
                    line = line.strip()

                    # Suche nach Größenangaben wie "4m3 Container"
                    size_match = re.search(r'(\d+)m3 Container', line)
                    if size_match:
                        current_size = f"{size_match.group(1)} m³"

                    # Suche nach Preisen wie "442,03 €"
                    price_match = re.match(r'^(\d{1,3}[.,]\d{2})\s*€$', line)
                    if price_match and current_size:
                        price = price_match.group(1)

                        product = {
                            "source": "Agrdar Container",
                            "title": f"{current_size} {waste_type}",
                            "type": waste_type,
                            "city": "Bochum",
                            "size": current_size,
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
                        self.log(f"  ✓ {current_size}: {price} EUR")
                        yield product

                        current_size = None  # Reset für nächsten Container

        except Exception as e:
            self.log(f"FEHLER: {e}")
            import traceback
            self.log(traceback.format_exc())

        self.log(f"\n{'='*80}")
        self.log(f"Gesamt gescrapt: {total_products} Produkte")
        self.log(f"{'='*80}\n")
