"""
Kreuz Containerdienst Spider
Extrahiert Preise für Container-Entsorgung in Köln
Shop: https://shop.kreuz-containerdienst.de/container-bestellen
"""

import logging
import re
from time import sleep

from scrapy import Spider

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC


class KreuzContainerdienstSpider(Spider):
    name = "kreuz-containerdienst"
    allowed_domains = ["shop.kreuz-containerdienst.de"]
    start_urls = ["https://shop.kreuz-containerdienst.de/container-bestellen"]

    # 9 Müllarten (URL-Slug -> Standardisierter Name)
    waste_categories = [
        ("absetzcontainer-fuer-baumischabfall", "Baumischabfall"),
        ("absetzcontainer-fuer-bauschutt", "Bauschutt"),
        ("absetzcontainer-fuer-altholz", "Altholz"),
        ("absetzcontainer-fuer-erdaushub-sauber", "Boden"),
        ("absetzcontainer-fuer-erdaushub-verunreinigt", "Boden verunreinigt"),
        ("absetzcontainer-fuer-gartenabfaelle", "Gartenabfälle"),
        ("absetzcontainer-fuer-gipsabfaelle", "Gips"),
        ("absetzcontainer-fuer-sperrmuell", "Sperrmüll"),
        ("absetzcontainer-fuer-dachpappe-bitumen", "Dachpappe"),
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
        self.log(f"Starte Kreuz Containerdienst Scraping (Köln)")
        self.log(f"{'='*80}\n")

        total_products = 0

        # Für jede Abfallart
        for url_slug, waste_type in self.waste_categories:
            self.log(f"\n--- Verarbeite: {waste_type} ---")

            try:
                url = f"https://shop.kreuz-containerdienst.de/produkt/{url_slug}/"
                self.driver.get(url)
                sleep(3)

                # Cookie-Banner akzeptieren (falls vorhanden)
                self._accept_cookies()

                # Container-Größen und Preise extrahieren
                products = self._extract_products(waste_type, url)

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

    def _accept_cookies(self):
        """Akzeptiert Cookie-Banner falls vorhanden."""
        try:
            # Suche nach Cookie-Banner Buttons
            cookie_selectors = [
                "//button[contains(text(), 'Akzeptieren')]",
                "//button[contains(text(), 'akzeptieren')]",
                "//a[contains(text(), 'Akzeptieren')]",
                "//button[contains(@class, 'cookie')]",
            ]
            for selector in cookie_selectors:
                try:
                    buttons = self.driver.find_elements(By.XPATH, selector)
                    for btn in buttons:
                        if btn.is_displayed():
                            self.driver.execute_script("arguments[0].click();", btn)
                            sleep(1)
                            return True
                except Exception:
                    pass
        except Exception:
            pass
        return False

    def _extract_products(self, waste_type, base_url):
        """Extrahiert alle Container-Größen und Preise von einer Produktseite."""
        products = []
        seen_sizes = set()

        try:
            # Warte auf Seite
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "form.variations_form, .product"))
            )

            # Finde Größen-Select (WooCommerce)
            size_select_id = "pa_containergroesse"

            try:
                select_elem = self.driver.find_element(By.ID, size_select_id)
                select = Select(select_elem)

                # Sammle alle Optionswerte zuerst (um Stale Element zu vermeiden)
                option_values = []
                for opt in select.options:
                    value = opt.get_attribute("value")
                    text = opt.text
                    if value and value.strip():
                        option_values.append((value, text))

                # Iteriere durch Optionen
                for value, text in option_values:
                    try:
                        # Finde Select neu (vermeidet Stale Element)
                        select_elem = self.driver.find_element(By.ID, size_select_id)
                        select = Select(select_elem)
                        select.select_by_value(value)
                        sleep(0.5)

                        # Wähle "ohne Deckel" falls vorhanden
                        try:
                            lid_select = Select(self.driver.find_element(By.ID, "pa_deckel_klappe"))
                            lid_select.select_by_value("ohne-deckel-oder-klappe-liefern")
                            sleep(0.5)
                        except Exception:
                            pass

                        # Größe aus Text extrahieren
                        size_match = re.search(r'(\d+)\s*[mM]', text)
                        if not size_match:
                            continue

                        size = size_match.group(1)

                        # BigBag überspringen
                        if 'bigbag' in text.lower() or 'big bag' in text.lower():
                            continue

                        # Duplikat-Check
                        if size in seen_sizes:
                            continue
                        seen_sizes.add(size)

                        # Preis extrahieren
                        price = self._get_current_price()
                        if not price:
                            continue

                        products.append({
                            "source": "Kreuz Containerdienst",
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
                            "URL": base_url
                        })

                    except Exception as e:
                        continue

            except Exception as e:
                self.log(f"  ⚠️ Select nicht gefunden: {e}")

        except Exception as e:
            self.log(f"  ⚠️ Fehler bei Extraktion: {e}")

        return products

    def _get_current_price(self):
        """Extrahiert den aktuell angezeigten Preis."""
        try:
            # Verschiedene Preis-Selektoren probieren
            price_selectors = [
                ".woocommerce-variation-price .woocommerce-Price-amount",
                ".woocommerce-variation-price .amount",
                ".single_variation_wrap .woocommerce-Price-amount",
                ".woocommerce-Price-amount.amount",
                ".price .amount",
            ]

            for selector in price_selectors:
                try:
                    price_elems = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    for price_elem in price_elems:
                        if price_elem and price_elem.is_displayed():
                            price_text = price_elem.text.strip()
                            if not price_text:
                                continue

                            # Preis extrahieren (deutsches Format: 449,00 €)
                            price_match = re.search(r'([\d.,]+)', price_text)
                            if price_match:
                                price = price_match.group(1)

                                # Tausendertrennzeichen entfernen falls vorhanden
                                if '.' in price and ',' in price:
                                    price = price.replace('.', '')

                                return price
                except Exception:
                    continue

        except Exception:
            pass
        return None
