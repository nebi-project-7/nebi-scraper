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
        """Extrahiert alle Produkte von einer Kategorieseite."""
        products = []

        try:
            # Warte auf Produktliste
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".product-box, .product-listing, .product"))
            )
        except:
            pass

        # HTML parsen
        sel = Selector(text=self.driver.page_source)

        # Finde alle Produkt-Boxen
        product_boxes = sel.css('.product-box, .card-body, .product-info')

        if not product_boxes:
            # Alternative: Suche nach Produkt-Links
            product_links = sel.xpath('//a[contains(@href, "/alle-abfaelle-containerdienst/") and contains(@href, "-cbm-")]/@href').getall()
            product_titles = sel.xpath('//a[contains(@href, "/alle-abfaelle-containerdienst/") and contains(@href, "-cbm-")]/text()').getall()

            # Fallback: Extrahiere aus dem sichtbaren Text
            page_text = self.driver.execute_script("return document.body.innerText;")

            # Pattern für Produkte: "X cbm ... €Y.YY"
            # Suche nach Zeilen mit cbm und Preisen
            lines = page_text.split('\n')

            current_size = None
            for line in lines:
                line = line.strip()

                # Überspringe BigBag
                if 'bigbag' in line.lower() or 'big bag' in line.lower() or 'big-bag' in line.lower():
                    continue

                # Suche nach Größe (z.B. "3 cbm Absetzcontainer")
                size_match = re.search(r'^(\d+)\s*cbm', line, re.IGNORECASE)
                if size_match:
                    current_size = size_match.group(1)

                # Suche nach Preis (z.B. "€329,33" oder "329,33 €")
                price_match = re.search(r'€?\s*(\d{1,3}(?:\.\d{3})*(?:,\d{2})?)\s*€?', line)
                if price_match and current_size:
                    price_str = price_match.group(1)
                    # Normalisiere Preis: "1.184,05" → "1184,05"
                    price = price_str.replace('.', '').replace(',', ',')

                    # Erstelle Produkt
                    product = {
                        "source": "EGGERS Container",
                        "title": f"{current_size} m³ {waste_type}",
                        "type": waste_type,
                        "city": "Hamburg",
                        "size": current_size,
                        "price": price,
                        "lid_price": "",
                        "arrival_price": "inklusive",
                        "departure_price": "inklusive",
                        "max_rental_period": "14",
                        "fee_after_max": "",
                        "cancellation_fee": "",
                        "URL": category_url
                    }
                    products.append(product)
                    current_size = None

        else:
            # Parse strukturierte Produkt-Boxen
            for box in product_boxes:
                try:
                    # Titel extrahieren
                    title = box.css('.product-name::text, .product-title::text, h2::text, h3::text').get()
                    if not title:
                        title = box.xpath('.//a/text()').get()

                    if not title:
                        continue

                    title = title.strip()

                    # Überspringe BigBag
                    if 'bigbag' in title.lower() or 'big bag' in title.lower():
                        continue

                    # Extrahiere Größe aus Titel
                    size_match = re.search(r'(\d+)\s*cbm', title, re.IGNORECASE)
                    if not size_match:
                        continue
                    size = size_match.group(1)

                    # Preis extrahieren
                    price_text = box.css('.product-price::text, .price::text').get()
                    if not price_text:
                        price_text = box.xpath('.//*[contains(@class, "price")]/text()').get()

                    if not price_text:
                        continue

                    # Normalisiere Preis
                    price_match = re.search(r'(\d{1,3}(?:\.\d{3})*(?:,\d{2})?)', price_text)
                    if not price_match:
                        continue

                    price = price_match.group(1).replace('.', '')

                    # URL extrahieren
                    product_url = box.css('a::attr(href)').get()
                    if product_url and not product_url.startswith('http'):
                        product_url = f"https://shop.eggers-gruppe.de{product_url}"
                    if not product_url:
                        product_url = category_url

                    product = {
                        "source": "EGGERS Container",
                        "title": f"{size} m³ {waste_type}",
                        "type": waste_type,
                        "city": "Hamburg",
                        "size": size,
                        "price": price,
                        "lid_price": "",
                        "arrival_price": "inklusive",
                        "departure_price": "inklusive",
                        "max_rental_period": "14",
                        "fee_after_max": "",
                        "cancellation_fee": "",
                        "URL": product_url
                    }
                    products.append(product)

                except Exception as e:
                    self.log(f"  ⚠️ Fehler beim Parsen eines Produkts: {e}")
                    continue

        return products
