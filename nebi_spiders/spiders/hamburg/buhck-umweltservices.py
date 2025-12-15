"""
Buhck Umweltservices Spider
Extrahiert Preise für Container-Entsorgung in Hamburg
Shop: https://buhck.shop/entsorgung
"""

import logging
import re
from time import sleep

from scrapy import Spider

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.common.exceptions import StaleElementReferenceException, NoSuchElementException


class BuhckUmweltservicesSpider(Spider):
    name = "buhck-umweltservices"
    allowed_domains = ["buhck.shop"]
    start_urls = ["https://buhck.shop/entsorgung"]

    # Produkt-URLs und standardisierte Namen
    waste_categories = [
        ("bauschutt-sw10044", "Bauschutt"),
        ("baumischabfall-sw10043", "Baumischabfall"),
        ("gruenschnitt-sw10047", "Gartenabfälle"),  # Immer "Gartenabfälle"
        ("altholz-sw10048", "Holz A1-A3"),  # ALTHOLZ -> Holz A1-A3
        ("entruempelungsabfall-sw10045", "Entrümpelungsabfall"),
        ("erdaushub-sw10046", "Boden"),
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
        self.plz = "22549"  # Zentrale Hamburg PLZ

    def closed(self, reason):
        try:
            self.driver.quit()
        except Exception:
            pass

    def parse(self, response):
        self.log(f"\n{'='*80}")
        self.log(f"Starte Buhck Umweltservices Scraping (PLZ {self.plz})")
        self.log(f"{'='*80}\n")

        total_products = 0

        for product_slug, waste_type in self.waste_categories:
            self.log(f"\n--- Verarbeite: {waste_type} ---")

            try:
                products = self._scrape_product_page(product_slug, waste_type)

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

    def _scrape_product_page(self, product_slug, waste_type):
        """Scrapt alle Container-Größen für eine Abfallart."""
        products = []
        url = f"https://buhck.shop/p/{product_slug}"

        self.driver.get(url)
        sleep(3)

        # Cookie-Banner entfernen
        self._dismiss_cookie_banner()

        # PLZ eingeben
        self._enter_plz()

        # Dropdown öffnen und Optionen sammeln
        size_options = self._get_size_options()

        if not size_options:
            self.log(f"  ⚠️ Keine Container-Größen gefunden")
            return products

        # Für jede Größe den Preis extrahieren
        for size, data_value in size_options:
            try:
                # Option auswählen
                self.driver.execute_script(f'''
                    var opt = document.querySelector('[data-value="{data_value}"]');
                    if (opt) opt.click();
                ''')
                sleep(1)

                # Preis aus JSON-LD extrahieren
                price = self._extract_price_from_jsonld()

                if price:
                    product = {
                        "source": "Buhck Umweltservices",
                        "title": f"{waste_type} {size} m³",
                        "type": waste_type,
                        "city": "Hamburg",
                        "size": size,
                        "price": price,
                        "lid_price": None,
                        "arrival_price": "inklusive",
                        "departure_price": "inklusive",
                        "max_rental_period": "5",
                        "fee_after_max": "3,57",
                        "cancellation_fee": None,
                        "URL": url
                    }
                    products.append(product)

                # Dropdown wieder öffnen
                self._open_dropdown()

            except StaleElementReferenceException:
                continue
            except Exception as e:
                self.log(f"  ⚠️ Fehler bei {size}m³: {e}")
                continue

        return products

    def _dismiss_cookie_banner(self):
        """Entfernt Cookie-Banner."""
        try:
            self.driver.execute_script("""
                document.querySelectorAll('#usercentrics-cmp-ui, [id*=usercentrics], [class*=consent]').forEach(e => e.remove());
            """)
            sleep(0.5)
        except:
            pass

    def _enter_plz(self):
        """Gibt PLZ ein."""
        try:
            plz_input = self.driver.find_element(By.NAME, "zipcode")
            plz_input.clear()
            plz_input.send_keys(self.plz)
            self.driver.execute_script("arguments[0].blur();", plz_input)
            sleep(2)
        except Exception as e:
            self.log(f"  ⚠️ PLZ-Eingabe fehlgeschlagen: {e}")

    def _open_dropdown(self):
        """Öffnet das Größen-Dropdown."""
        try:
            self.driver.execute_script("""
                var selectize = document.querySelector('.selectize-control .selectize-input');
                if (selectize) selectize.click();
            """)
            sleep(0.5)
        except:
            pass

    def _get_size_options(self):
        """Holt alle Container-Größen aus dem Dropdown."""
        options = []

        try:
            # Dropdown öffnen
            self._open_dropdown()
            sleep(1)

            # Optionen finden
            dropdown_content = self.driver.find_element(By.CSS_SELECTOR, ".selectize-dropdown-content")
            option_elements = dropdown_content.find_elements(By.CSS_SELECTOR, "[data-value]")

            for opt in option_elements:
                try:
                    data_value = opt.get_attribute('data-value')
                    text = opt.text.strip()

                    # BigBag überspringen
                    if 'big bag' in text.lower() or 'bag' in text.lower():
                        continue

                    # Größe extrahieren (z.B. "3 cbm" -> "3")
                    size_match = re.search(r'(\d+)\s*cbm', text, re.IGNORECASE)
                    if size_match:
                        size = size_match.group(1)
                        options.append((size, data_value))

                except StaleElementReferenceException:
                    continue

        except Exception as e:
            self.log(f"  ⚠️ Dropdown-Fehler: {e}")

        return options

    def _extract_price_from_jsonld(self):
        """Extrahiert Preis aus JSON-LD Daten."""
        try:
            scripts = self.driver.find_elements(By.CSS_SELECTOR, "script[type='application/ld+json']")

            for script in scripts:
                content = script.get_attribute('innerHTML')
                if 'price' in content.lower():
                    # Preis finden (z.B. "price": 373.07 oder "price": "373.07")
                    price_match = re.search(r'"price"[:\s]+"?([\d.]+)"?', content)
                    if price_match:
                        price = price_match.group(1)
                        # In deutsches Format konvertieren (373.07 -> 373,07)
                        price_de = price.replace('.', ',')
                        return price_de

            return None

        except Exception as e:
            return None
