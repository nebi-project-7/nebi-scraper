"""
WEGRO Container Spider
Extrahiert Preise für Container-Entsorgung in Hamburg
Shop: https://www.wegrogmbh.de/shop/
"""

import logging
import re
from time import sleep

from scrapy import Spider
from scrapy.selector import Selector

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


class WegroContainerSpider(Spider):
    name = "wegro-container"
    allowed_domains = ["wegrogmbh.de"]
    start_urls = ["https://www.wegrogmbh.de/shop/"]

    # Kategorien mit ihren URLs und standardisierten Namen
    waste_categories = [
        ("bauschutt", "Bauschutt"),
        ("baustellenabfall-mit-mineralik-gips", "Baumischabfall gipshaltig"),
        ("baustellenabfall-o.-mineralik", "Baumischabfall"),
        ("erdaushub-bauschutt-zum-pauschalpreis-inklusive-transport", "Boden"),
        ("teer-und-dachpappe", "Dachpappe"),
        ("gartenabfaelle", "Gartenabfälle"),
        ("altholz", "Holz A4"),
        ("altholz,-unbehandelt", "Holz A1-A3"),
        ("daemmmaterialien", "Dämmstoffe"),
        ("porenbeton", "Porenbeton"),
        ("rigips-gipskarton", "Gips"),
        ("sperrmuell", "Sperrmüll"),
        # ("asbestabfaelle", "Asbest"),  # Entfernt - spezielle Anforderungen
        # ("eisenschrott-metalle", "Schrott"),  # Entfernt - meist kostenlos/Ankauf
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
        self.driver = webdriver.Chrome(options=options)

        self.seen_products = set()

    def closed(self, reason):
        try:
            self.driver.quit()
        except Exception:
            pass

    def parse(self, response):
        self.log(f"\n{'='*80}")
        self.log(f"Starte WEGRO Container Scraping (Hamburg)")
        self.log(f"{'='*80}\n")

        total_products = 0

        for category_slug, waste_type in self.waste_categories:
            category_url = f"https://www.wegrogmbh.de/{category_slug}/"
            self.log(f"\n--- Verarbeite: {waste_type} ---")

            try:
                self.driver.get(category_url)
                sleep(3)

                # Cookie-Banner schließen
                self._dismiss_cookie_banner()

                # Produkte extrahieren
                products = self._extract_products(waste_type, category_url)

                for product in products:
                    product_key = f"{product['type']}|{product['size']}"
                    if product_key not in self.seen_products:
                        self.seen_products.add(product_key)
                        total_products += 1
                        self.log(f"  ✓ {product['size']}m³: {product['price']}€")
                        yield product

            except Exception as e:
                self.log(f"  ❌ Fehler bei {waste_type}: {e}")
                continue

        self.log(f"\n{'='*80}")
        self.log(f"✓ Gesamt gescrapt: {total_products} Produkte")
        self.log(f"{'='*80}\n")

    def _dismiss_cookie_banner(self):
        """Schließt Cookie-Banner."""
        try:
            cookie_buttons = self.driver.find_elements(
                By.XPATH,
                "//button[contains(text(), 'Akzeptieren') or contains(text(), 'Accept') or contains(@class, 'accept') or contains(@id, 'accept')]"
            )
            for btn in cookie_buttons:
                try:
                    if btn.is_displayed():
                        btn.click()
                        sleep(1)
                        return
                except:
                    pass
        except:
            pass

    def _extract_products(self, waste_type, category_url):
        """Extrahiert alle Produkte von einer Kategorieseite via PHP-Debug-Dumps."""
        products = []
        import html

        page_source = self.driver.page_source

        # Dekodiere HTML-Entities (&#91; -> [, &#93; -> ])
        decoded_source = html.unescape(page_source)

        # Suche nach PHP-Array-Dumps mit Produktdaten
        # Format: [alias] => 3,5cbm-container-mit-klappe-bauschutt ... [price] => 385.56
        product_pattern = re.findall(
            r'\[alias\]\s*=>\s*(\S+cbm[^\s\[]+).*?\[price\]\s*=>\s*(\d+\.?\d*)',
            decoded_source,
            re.DOTALL
        )

        for alias, price in product_pattern:
            try:
                # Überspringe BigBag und Behälter
                if any(x in alias.lower() for x in ['bigbag', 'big-bag', 'behaelter']):
                    continue

                # Extrahiere Größe aus Alias
                size_match = re.search(r'(\d+(?:,\d+)?)\s*cbm', alias, re.IGNORECASE)
                if not size_match:
                    continue

                size = size_match.group(1).replace(',', '.')

                # Preis formatieren (385.56 → "385,56")
                price_float = float(price)
                price_str = f"{price_float:.2f}".replace('.', ',')

                product_url = f"https://www.wegrogmbh.de/{alias}"

                product = {
                    "source": "WEGRO Container",
                    "title": f"{size} m³ {waste_type}",
                    "type": waste_type,
                    "city": "Hamburg",
                    "size": size,
                    "price": price_str,
                    "lid_price": "",
                    "arrival_price": "inklusive",
                    "departure_price": "inklusive",
                    "max_rental_period": "7",
                    "fee_after_max": "2,98€",
                    "cancellation_fee": "153,51€",
                    "URL": product_url
                }
                products.append(product)

            except Exception as e:
                self.log(f"  ⚠️ Fehler beim Parsen: {e}")
                continue

        if products:
            self.log(f"  ✓ {len(products)} Produkte extrahiert")

        return products
