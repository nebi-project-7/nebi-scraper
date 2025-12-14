"""
EGGERS Container Spider
Extrahiert Preise für Container-Entsorgung in Hamburg
Shop: https://shop.eggers-gruppe.de/
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


class EggersContainerSpider(Spider):
    name = "eggers-container"
    allowed_domains = ["shop.eggers-gruppe.de"]
    start_urls = ["https://shop.eggers-gruppe.de/alle-abfaelle-containerdienst/"]

    # Kategorien mit ihren URLs und standardisierten Namen
    waste_categories = [
        ("altholz-unbehandelt", "Holz A1-A3"),
        ("altholz-behandelt-a4", "Holz A4"),
        ("asbest", "Asbest"),
        ("baumischabfall", "Baumischabfall"),
        ("baumischabfall-gipshaltig", "Baumischabfall gipshaltig"),
        ("bauschutt", "Bauschutt"),
        ("beton", "Beton"),
        ("boden", "Boden"),
        ("boden-bauschutt-gemisch", "Boden-Bauschutt-Gemisch"),
        ("dachpappe", "Dachpappe"),
        ("dachpappe-mit-anhaftungen", "Dachpappe mit Anhaftungen"),
        ("gartenabfall", "Gartenabfälle"),
        ("gipsabfall", "Gips"),
        ("mineralfaserdaemmung-kmf", "Dämmstoffe"),
        ("porenbeton-ytong", "Porenbeton"),
        ("sperrmuell", "Sperrmüll"),
        ("stubben-und-stammholz", "Stubben und Stammholz"),
        ("styropor-daemmung-eps", "Styropor"),
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

        # Set zur Vermeidung von Duplikaten
        self.seen_products = set()

    def closed(self, reason):
        try:
            self.driver.quit()
        except Exception:
            pass

    def parse(self, response):
        self.log(f"\n{'='*80}")
        self.log(f"Starte EGGERS Container Scraping (Hamburg)")
        self.log(f"{'='*80}\n")

        total_products = 0

        for category_slug, waste_type in self.waste_categories:
            category_url = f"https://shop.eggers-gruppe.de/alle-abfaelle-containerdienst/{category_slug}/"
            self.log(f"\n--- Verarbeite: {waste_type} ---")

            try:
                self.driver.get(category_url)
                sleep(3)

                # Cookie-Banner schließen
                self._dismiss_cookie_banner()

                # Produkte auf der Kategorieseite finden
                products = self._extract_products_from_category(waste_type, category_url)

                for product in products:
                    # Duplikat-Check
                    product_key = f"{product['type']}|{product['size']}"
                    if product_key not in self.seen_products:
                        self.seen_products.add(product_key)
                        total_products += 1
                        self.log(f"  ✓ {product['size']}m³: {product['price']}€")
                        yield product
                    else:
                        self.log(f"  ⚠️ Duplikat übersprungen: {product['type']} {product['size']}m³")

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
                "//button[contains(text(), 'Akzeptieren') or contains(text(), 'Accept') or contains(text(), 'Alle akzeptieren') or contains(@class, 'accept')]"
            )
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

    def _extract_products_from_category(self, waste_type, category_url):
        """Extrahiert alle Produkte von einer Kategorieseite via Google Analytics JSON."""
        products = []
        import json

        # HTML Quellcode holen
        page_source = self.driver.page_source

        # Suche nach Google Analytics view_item_list Event mit Produktdaten
        # Format: gtag('event', 'view_item_list', {"currency": 'EUR',"items": [...]})
        ga_pattern = re.search(
            r"gtag\('event',\s*'view_item_list',\s*(\{.*?\])\s*\}\)",
            page_source,
            re.DOTALL
        )

        if ga_pattern:
            try:
                # JSON-ähnlichen String extrahieren und bereinigen
                json_str = ga_pattern.group(1) + '}'
                # Einfache Anführungszeichen durch doppelte ersetzen
                json_str = json_str.replace("'", '"')
                # Parse JSON
                ga_data = json.loads(json_str)
                items = ga_data.get('items', [])

                for item in items:
                    item_name = item.get('item_name', '')
                    price = item.get('price', 0)

                    # Überspringe BigBag
                    if 'bigbag' in item_name.lower() or 'big bag' in item_name.lower():
                        continue

                    # Extrahiere Größe aus item_name (z.B. "3 cbm Absetzcontainer")
                    size_match = re.search(r'(\d+)\s*cbm', item_name, re.IGNORECASE)
                    if not size_match:
                        continue

                    size = size_match.group(1)

                    # Preis formatieren (329.33 → "329,33")
                    price_str = f"{price:.2f}".replace('.', ',')

                    product = {
                        "source": "EGGERS Container",
                        "title": f"{size} m³ {waste_type}",
                        "type": waste_type,
                        "city": "Hamburg",
                        "size": size,
                        "price": price_str,
                        "lid_price": "",
                        "arrival_price": "inklusive",
                        "departure_price": "inklusive",
                        "max_rental_period": "14",
                        "fee_after_max": "5,95€",
                        "cancellation_fee": "",
                        "URL": category_url
                    }
                    products.append(product)

                self.log(f"  ✓ {len(products)} Produkte via GA-Daten extrahiert")

            except json.JSONDecodeError as e:
                self.log(f"  ⚠️ JSON Parse Fehler: {e}")

        # Fallback: Preis-Elemente im HTML suchen
        if not products:
            sel = Selector(text=page_source)

            # Suche nach Produkt-Boxen mit Preis
            product_boxes = sel.css('.product-box, .box--content, .product-info')

            for box in product_boxes:
                try:
                    # Titel/Name extrahieren
                    title = box.css('.product-name a::text, .product-title::text, a.product-name::text').get()
                    if not title:
                        title = box.xpath('.//a[contains(@class, "product")]/text()').get()
                    if not title:
                        continue

                    title = title.strip()

                    # Überspringe BigBag
                    if 'bigbag' in title.lower() or 'big bag' in title.lower():
                        continue

                    # Extrahiere Größe
                    size_match = re.search(r'(\d+)\s*cbm', title, re.IGNORECASE)
                    if not size_match:
                        continue
                    size = size_match.group(1)

                    # Preis extrahieren - suche nach price--default Klasse
                    price_elem = box.css('.price--default::text, .product-price::text, span.price::text').get()
                    if not price_elem:
                        price_elem = box.xpath('.//*[contains(@class, "price")]//text()').get()

                    if not price_elem:
                        continue

                    # Preis bereinigen (z.B. "329,33 €" → "329,33")
                    price_match = re.search(r'(\d{1,3}(?:\.\d{3})*(?:,\d{2}))', price_elem)
                    if not price_match:
                        continue

                    price_str = price_match.group(1).replace('.', '')

                    product = {
                        "source": "EGGERS Container",
                        "title": f"{size} m³ {waste_type}",
                        "type": waste_type,
                        "city": "Hamburg",
                        "size": size,
                        "price": price_str,
                        "lid_price": "",
                        "arrival_price": "inklusive",
                        "departure_price": "inklusive",
                        "max_rental_period": "14",
                        "fee_after_max": "5,95€",
                        "cancellation_fee": "",
                        "URL": category_url
                    }
                    products.append(product)

                except Exception as e:
                    self.log(f"  ⚠️ Fehler beim Parsen: {e}")
                    continue

            if products:
                self.log(f"  ✓ {len(products)} Produkte via HTML extrahiert")

        return products
