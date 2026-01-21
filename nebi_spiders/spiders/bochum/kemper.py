"""
Kemper Containerdienst Spider
Extrahiert Preise für Container-Entsorgung in Bochum
Website: https://www.containerdienst-kemper.de/container-online-bestellen/
"""

import json
import logging
import urllib.parse
from time import sleep

from scrapy import Spider

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager


class KemperSpider(Spider):
    name = "kemper"
    allowed_domains = ["containerdienst-kemper.de"]
    start_urls = ["https://www.containerdienst-kemper.de/container-online-bestellen/"]

    # Produktseiten mit Abfallarten
    PRODUCT_PAGES = [
        ("https://www.containerdienst-kemper.de/container-online-bestellen/produkt/baumischabfaelle/", "Baumischabfall"),
        ("https://www.containerdienst-kemper.de/container-online-bestellen/produkt/bauschutt/", "Bauschutt"),
        ("https://www.containerdienst-kemper.de/container-online-bestellen/produkt/gips/", "Gips"),
        ("https://www.containerdienst-kemper.de/container-online-bestellen/produkt/boden-steine/", "Boden"),
        ("https://www.containerdienst-kemper.de/container-online-bestellen/produkt/gruenschnitt/", "Gartenabfälle"),
        ("https://www.containerdienst-kemper.de/container-online-bestellen/produkt/holz-a-4/", "Holz A4"),
        ("https://www.containerdienst-kemper.de/container-online-bestellen/produkt/holz-a1-bis-a3/", "Holz A1-A3"),
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
        self.log(f"Starte Kemper Containerdienst Scraping für Bochum")
        self.log(f"{'='*80}\n")

        total_products = 0

        try:
            for url, waste_type in self.PRODUCT_PAGES:
                self.log(f"\n--- {waste_type} ---")

                self.driver.get(url)
                sleep(2)

                # Finde das Form mit den Variationen (WooCommerce)
                forms = self.driver.find_elements(By.TAG_NAME, "form")
                for form in forms:
                    variations_json = form.get_attribute("data-product_variations")
                    if variations_json:
                        variations = json.loads(variations_json)
                        for var in variations:
                            # Attribut dekodieren
                            attr = var.get("attributes", {})
                            size_encoded = attr.get("attribute_pa_fassungsvermoegen", "")
                            size_decoded = urllib.parse.unquote(size_encoded)

                            # Größe formatieren
                            size = self._format_size(size_decoded)

                            # Preis
                            price_float = var.get("display_price", 0)
                            price_str = f"{price_float:.2f}".replace('.', ',')

                            product = {
                                "source": "Kemper Containerdienst",
                                "title": f"{size} {waste_type}",
                                "type": waste_type,
                                "city": "Bochum",
                                "size": size,
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
                            self.log(f"  ✓ {size}: {price_str} EUR")
                            yield product

                        break

        except Exception as e:
            self.log(f"FEHLER: {e}")
            import traceback
            self.log(traceback.format_exc())

        self.log(f"\n{'='*80}")
        self.log(f"Gesamt gescrapt: {total_products} Produkte")
        self.log(f"{'='*80}\n")

    def _format_size(self, size_encoded):
        """Formatiert die Größe aus dem URL-kodierten String."""
        # "55-m%c2%b3-mit-klappe" -> "5,5 m³"
        # "3-m%c2%b3" -> "3 m³"
        size = size_encoded.replace("-", " ").strip()

        # "mit klappe" entfernen für einheitliche Darstellung
        size = size.lower().replace("mit klappe", "").strip()

        # "55" -> "5,5"
        if size.startswith("55 "):
            size = "5,5 " + size[3:]

        # Bereinigen von mehrfachen Leerzeichen
        while "  " in size:
            size = size.replace("  ", " ")

        # Sicherstellen dass "m³" vorhanden ist
        if "m³" not in size:
            size = size + " m³"

        return size.strip()
