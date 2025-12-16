"""
RAVOS Containerdienst Spider
Extrahiert Preise für Container-Entsorgung in Köln
Shop: https://ravos.de/containerdienst/containerdienst/
"""

import logging
import re
from time import sleep

from scrapy import Spider

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, TimeoutException


class RavosContainerdienstSpider(Spider):
    name = "ravos-containerdienst"
    allowed_domains = ["ravos.de"]
    start_urls = ["https://ravos.de/containerdienst/containerdienst/"]

    # Produkt-URLs und standardisierte Namen (5 Müllarten)
    waste_categories = [
        ("https://ravos.de/produkt/container-bauschutt/", "Bauschutt"),
        ("https://ravos.de/produkt/container-baumischabfall/", "Baumischabfall"),
        ("https://ravos.de/produkt/container-gruenschnitt/", "Gartenabfälle"),
        ("https://ravos.de/produkt/container-holzabfall/", "Holz A1-A3"),
        ("https://ravos.de/produkt/container-erdaushub/", "Boden"),
    ]

    faq_url = "https://ravos.de/faq/"

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
        # Default-Werte (werden dynamisch überschrieben)
        self.max_rental_period = "14"
        self.fee_after_max = "5,95"
        self.cancellation_fees = "Zone 1: 120€, Zone 2: 145€, Zone 3: 205€, Zone 4: 240€"

    def closed(self, reason):
        try:
            self.driver.quit()
        except Exception:
            pass

    def parse(self, response):
        self.log(f"\n{'='*80}")
        self.log(f"Starte RAVOS Containerdienst Scraping (Köln)")
        self.log(f"{'='*80}\n")

        total_products = 0

        # Zuerst FAQ-Seite scrapen für Stellzeit und Fehlfahrten
        self._scrape_faq_info()

        for product_url, waste_type in self.waste_categories:
            self.log(f"\n--- Verarbeite: {waste_type} ---")

            try:
                products = self._scrape_product_page(product_url, waste_type)

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

    def _scrape_faq_info(self):
        """Scrapt Stellzeit und Fehlfahrten-Infos von der FAQ-Seite."""
        try:
            self.log(f"📋 Lade FAQ-Seite: {self.faq_url}")
            self.driver.get(self.faq_url)
            sleep(2)

            page_text = self.driver.page_source

            # Stellzeit extrahieren (z.B. "14 Tage mietfrei")
            stellzeit_match = re.search(r'(\d+)\s*Tage\s*mietfrei', page_text, re.IGNORECASE)
            if stellzeit_match:
                self.max_rental_period = stellzeit_match.group(1)
                self.log(f"  ✓ Stellzeit mietfrei: {self.max_rental_period} Tage")

            # Miete pro Tag extrahieren (z.B. "5,95 €" oder "5.95 €")
            miete_match = re.search(r'Miete\s*von\s*(\d+[,\.]\d+)\s*€', page_text, re.IGNORECASE)
            if miete_match:
                self.fee_after_max = miete_match.group(1).replace('.', ',')
                self.log(f"  ✓ Miete pro Tag: {self.fee_after_max}€")

            # Fehlfahrten-Zonen extrahieren
            zone_pattern = r'Zone\s*1:\s*(\d+)\s*€.*?Zone\s*2:\s*(\d+)\s*€.*?Zone\s*3:\s*(\d+)\s*€.*?Zone\s*4:\s*(\d+)\s*€'
            zone_match = re.search(zone_pattern, page_text, re.IGNORECASE | re.DOTALL)
            if zone_match:
                z1, z2, z3, z4 = zone_match.groups()
                self.cancellation_fees = f"Zone 1: {z1}€, Zone 2: {z2}€, Zone 3: {z3}€, Zone 4: {z4}€"
                self.log(f"  ✓ Fehlfahrten: {self.cancellation_fees}")

        except Exception as e:
            self.log(f"  ⚠️ Fehler beim FAQ-Scraping: {e}")

    def _scrape_product_page(self, url, waste_type):
        """Scrapt alle Container-Größen für eine Abfallart."""
        products = []

        self.driver.get(url)
        sleep(2)

        # Cookie-Banner entfernen falls vorhanden
        self._dismiss_cookie_banner()

        # Dropdown für Container-Größen finden
        try:
            # WooCommerce Variation Dropdown suchen
            dropdown = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "select[name='attribute_pa_container-groesse'], select[id*='container'], select.variations select"))
            )

            options = dropdown.find_elements(By.TAG_NAME, "option")

            for option in options:
                try:
                    value = option.get_attribute('value')
                    text = option.text.strip()

                    if not value or value == "" or "wählen" in text.lower():
                        continue

                    # Größe extrahieren (z.B. "3 m³" oder "3m³" oder "3 cbm")
                    size_match = re.search(r'(\d+)\s*(?:m³|m3|cbm)', text, re.IGNORECASE)
                    if not size_match:
                        # Versuche nur Zahl zu finden
                        size_match = re.search(r'^(\d+)', text)

                    if not size_match:
                        continue

                    size = size_match.group(1)

                    # Option auswählen
                    option.click()
                    sleep(1)

                    # Preis extrahieren
                    price = self._extract_price()

                    if price:
                        product = {
                            "source": "RAVOS Containerdienst",
                            "title": f"{waste_type} {size} m³",
                            "type": waste_type,
                            "city": "Köln",
                            "size": size,
                            "price": price,
                            "lid_price": None,
                            "arrival_price": "inklusive",
                            "departure_price": "inklusive",
                            "max_rental_period": self.max_rental_period,
                            "fee_after_max": self.fee_after_max,
                            "cancellation_fee": self.cancellation_fees,
                            "URL": url
                        }
                        products.append(product)

                except Exception as e:
                    continue

        except TimeoutException:
            self.log(f"  ⚠️ Kein Dropdown gefunden, versuche alternative Methode")
            # Alternative: Preise direkt aus der Seite extrahieren
            products = self._extract_prices_from_page(url, waste_type)

        except Exception as e:
            self.log(f"  ⚠️ Dropdown-Fehler: {e}")

        return products

    def _extract_prices_from_page(self, url, waste_type):
        """Alternative Methode: Preise aus dem versteckten Select-Element extrahieren."""
        products = []
        seen_sizes = set()

        try:
            page_source = self.driver.page_source

            # Pattern für verstecktes Select mit data-containersize_cost
            # Format: value="3 m³ Container|0|" data-containersize_cost="269"
            pattern = r'value="([^"]*m[³3][^"]*)"[^>]*data-containersize_cost="(\d+)"'
            matches = re.findall(pattern, page_source, re.IGNORECASE)

            for option_text, price in matches:
                # Größe aus Option-Text extrahieren (z.B. "3 m³ Container" oder "5,5 m³ Container")
                size_match = re.search(r'(\d+(?:[.,]\d+)?)\s*m[³3]', option_text)
                if not size_match:
                    continue

                size_raw = size_match.group(1).replace(',', '.')
                # Runde auf ganze Zahl (5.5 -> 5)
                try:
                    size = str(int(float(size_raw)))
                except:
                    size = size_raw.split('.')[0] if '.' in size_raw else size_raw

                if size in seen_sizes:
                    continue
                seen_sizes.add(size)

                # Preis formatieren (269 -> 269,00)
                price_clean = f"{price},00"

                product = {
                    "source": "RAVOS Containerdienst",
                    "title": f"{waste_type} {size} m³",
                    "type": waste_type,
                    "city": "Köln",
                    "size": size,
                    "price": price_clean,
                    "lid_price": None,
                    "arrival_price": "inklusive",
                    "departure_price": "inklusive",
                    "max_rental_period": self.max_rental_period,
                    "fee_after_max": self.fee_after_max,
                    "cancellation_fee": self.cancellation_fees,
                    "URL": url
                }
                products.append(product)

        except Exception as e:
            self.log(f"  ⚠️ Alternative Extraktion fehlgeschlagen: {e}")

        return products

    def _dismiss_cookie_banner(self):
        """Entfernt Cookie-Banner."""
        try:
            # Versuche verschiedene Cookie-Banner zu schließen
            selectors = [
                "button[id*='accept']",
                "button[class*='accept']",
                "a[id*='accept']",
                ".cookie-accept",
                "#cookie-accept",
                "button[data-action='accept']",
            ]

            for selector in selectors:
                try:
                    btn = self.driver.find_element(By.CSS_SELECTOR, selector)
                    btn.click()
                    sleep(0.5)
                    return
                except NoSuchElementException:
                    continue

        except Exception:
            pass

    def _extract_price(self):
        """Extrahiert den aktuellen Preis aus der Seite."""
        try:
            # WooCommerce Preis-Elemente
            price_selectors = [
                ".woocommerce-variation-price .amount",
                ".price .amount",
                ".woocommerce-Price-amount",
                "span.price",
                ".summary .price .amount",
            ]

            for selector in price_selectors:
                try:
                    price_elem = self.driver.find_element(By.CSS_SELECTOR, selector)
                    price_text = price_elem.text.strip()

                    if price_text:
                        # Bereinige Preis
                        price_clean = re.sub(r'[^\d,\.]', '', price_text)

                        if not price_clean:
                            continue

                        # Konvertiere zu deutschem Format
                        if ',' in price_clean and '.' in price_clean:
                            # Gemischt: bestimme Dezimaltrenner
                            if price_clean.rfind(',') > price_clean.rfind('.'):
                                # Deutsch: 1.234,56
                                price_clean = price_clean.replace('.', '')
                            else:
                                # Englisch: 1,234.56
                                price_clean = price_clean.replace(',', '').replace('.', ',')
                        elif '.' in price_clean:
                            # Nur Punkt - zu Komma konvertieren
                            parts = price_clean.split('.')
                            if len(parts) == 2 and len(parts[1]) == 2:
                                price_clean = price_clean.replace('.', ',')
                            else:
                                price_clean = price_clean.replace('.', '')

                        if price_clean and price_clean != "0":
                            return price_clean

                except NoSuchElementException:
                    continue

            return None

        except Exception as e:
            return None
