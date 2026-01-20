"""
Schmalkowski Spider
Extrahiert Preise für Container-Entsorgung in Bochum
Website: https://www.schmalkowski.de/online-container-bestellen/
Bochum = Entfernungszone 2 (+23,80 EUR pro Lieferung)
"""

import re
import logging
from time import sleep

from scrapy import Spider

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager


class SchmalkowskiSpider(Spider):
    name = "schmalkowski"
    allowed_domains = ["schmalkowski.de"]
    start_urls = ["https://www.schmalkowski.de/online-container-bestellen/index.php"]

    # Entfernungszuschlag Zone 2 (Bochum)
    ZONE_2_SURCHARGE = 23.80

    # Abfallarten mit URLs
    WASTE_PAGES = [
        ("https://www.schmalkowski.de/online-container-bestellen/container-fuer-bauschutt/index.php", "Bauschutt"),
        ("https://www.schmalkowski.de/online-container-bestellen/container-fuer-boden/index.php", "Boden"),
        ("https://www.schmalkowski.de/online-container-bestellen/container-fuer-gips---gasbeton/index.php", "Gips"),
        ("https://www.schmalkowski.de/online-container-bestellen/container-fuer-holz/index.php", "Holz A1-A3"),
        ("https://www.schmalkowski.de/online-container-bestellen/container-fuer-gartenabfall/index.php", "Gartenabfälle"),
        ("https://www.schmalkowski.de/online-container-bestellen/container-fuer-gemischten-abfall/index.php", "Sperrmüll"),
        ("https://www.schmalkowski.de/online-container-bestellen/container-fuer-baumischabfaelle/index.php", "Baumischabfall"),
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
        self.log(f"Starte Schmalkowski Scraping für Bochum (Zone 2)")
        self.log(f"{'='*80}\n")

        total_products = 0

        try:
            for url, waste_type in self.WASTE_PAGES:
                self.log(f"\n--- {waste_type} ---")

                self.driver.get(url)
                sleep(2)

                body_text = self.driver.find_element(By.TAG_NAME, "body").text
                lines = body_text.split('\n')

                current_size = None

                for i, line in enumerate(lines):
                    line = line.strip()

                    # Suche nach "Xer Container"
                    size_match = re.match(r'^(\d+)er Container', line)
                    if size_match:
                        current_size = size_match.group(1)

                    # Suche nach Preisen wie "215,00 EUR"
                    price_match = re.match(r'^([\d.,]+)\s*EUR', line)
                    if price_match and current_size:
                        base_price = price_match.group(1).replace('.', '').replace(',', '.')
                        base_price_float = float(base_price)

                        # Addiere Entfernungszuschlag Zone 2
                        total_price = base_price_float + self.ZONE_2_SURCHARGE
                        price_str = f"{total_price:.2f}".replace('.', ',')

                        product = {
                            "source": "Schmalkowski",
                            "title": f"{current_size} m³ {waste_type}",
                            "type": waste_type,
                            "city": "Bochum",
                            "size": f"{current_size} m³",
                            "price": price_str,
                            "lid_price": "auf Anfrage",
                            "arrival_price": "inklusive",
                            "departure_price": "inklusive",
                            "max_rental_period": "14 Tage",
                            "fee_after_max": "auf Anfrage",
                            "cancellation_fee": None,
                            "URL": url
                        }

                        total_products += 1
                        self.log(f"  ✓ {current_size} m³: {price_str} EUR (inkl. Zone 2)")
                        yield product

                        current_size = None

        except Exception as e:
            self.log(f"FEHLER: {e}")
            import traceback
            self.log(traceback.format_exc())

        self.log(f"\n{'='*80}")
        self.log(f"Gesamt gescrapt: {total_products} Produkte")
        self.log(f"{'='*80}\n")
