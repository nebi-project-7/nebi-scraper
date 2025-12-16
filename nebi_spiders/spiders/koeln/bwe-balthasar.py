"""
BWE Balthasar Spider
Extrahiert Preise für Container-Entsorgung in Köln
Shop: https://www.bwe-koeln.de/subpages/abfallart.php
"""

import logging
import re
from time import sleep

from scrapy import Spider

from selenium import webdriver
from selenium.webdriver.common.by import By


class BweBalthasarSpider(Spider):
    name = "bwe-balthasar"
    allowed_domains = ["bwe-koeln.de"]
    start_urls = ["https://www.bwe-koeln.de/subpages/abfallart.php"]

    # PLZ für Köln
    plz = "50968"

    # 9 Müllarten (URL-Parameter -> Standardisierter Name)
    waste_categories = [
        ("bauschutt", "Bauschutt"),
        ("baustellenabfall", "Baumischabfall"),
        ("gruenschnitt", "Gartenabfälle"),
        ("sperrmuell", "Sperrmüll"),
        ("holz", "Holz A1-A3"),
        ("erde", "Boden"),
        ("gipsabfall", "Gips"),
        ("metallabfall", "Metallschrott"),
        ("papier", "Papier/Pappe"),
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
        self.log(f"Starte BWE Balthasar Scraping (Köln)")
        self.log(f"{'='*80}\n")

        total_products = 0

        # Für jede Abfallart - direkt per URL aufrufen
        for url_param, waste_type in self.waste_categories:
            self.log(f"\n--- Verarbeite: {waste_type} ---")

            try:
                # Direkte URL mit PLZ und Abfallart
                url = f"https://www.bwe-koeln.de/subpages/container.php?plz={self.plz}&abfall={url_param}"
                self.driver.get(url)
                sleep(2)

                # Container-Artikel extrahieren
                articles = self.driver.find_elements(By.CSS_SELECTOR, ".container-artikel")

                if not articles:
                    self.log(f"  ⚠️ Keine Container gefunden")
                    continue

                # Größen und Preise extrahieren (deduplizieren)
                seen_sizes = set()

                for article in articles:
                    try:
                        text = article.text

                        # BigBag überspringen
                        if 'bigbag' in text.lower() or 'big bag' in text.lower():
                            continue

                        # Größe extrahieren
                        size_match = re.search(r'(\d+)m³', text)
                        if not size_match:
                            continue
                        size = size_match.group(1)

                        # Duplikat-Check (gleiche Größe kann mehrfach angezeigt werden)
                        if size in seen_sizes:
                            continue
                        seen_sizes.add(size)

                        # Preis extrahieren
                        price_match = re.search(r'([\d,.]+)€', text)
                        if not price_match:
                            continue

                        price = price_match.group(1)
                        # Stelle sicher, dass Preis deutsches Format hat
                        if '.' in price and ',' in price:
                            # 1.234,56 Format - OK
                            pass
                        elif '.' in price:
                            # Englisches Format oder Tausender
                            parts = price.split('.')
                            if len(parts) == 2 and len(parts[1]) == 2:
                                price = price.replace('.', ',')

                        # Produkt-Key für globale Duplikat-Prüfung
                        product_key = f"{waste_type}|{size}"
                        if product_key in self.seen_products:
                            continue
                        self.seen_products.add(product_key)

                        total_products += 1
                        self.log(f"  ✓ {size}m³: {price}€")

                        yield {
                            "source": "BWE Balthasar",
                            "title": f"{waste_type} {size} m³",
                            "type": waste_type,
                            "city": "Köln",
                            "size": size,
                            "price": price,
                            "lid_price": None,
                            "arrival_price": "inklusive",
                            "departure_price": "inklusive",
                            "max_rental_period": "14",
                            "fee_after_max": None,
                            "cancellation_fee": None,
                            "URL": url
                        }

                    except Exception as e:
                        continue

            except Exception as e:
                self.log(f"  ❌ Fehler bei {waste_type}: {e}")
                continue

        self.log(f"\n{'='*80}")
        self.log(f"✓ Gesamt gescrapt: {total_products} Produkte")
        self.log(f"{'='*80}\n")
