"""
Redooo Hannover Spider
Extrahiert Preise für Container-Entsorgung in Hannover
Shop: https://www.redooo.de/privatkunden
"""

import logging
import re
from time import sleep

from scrapy import Spider

from selenium import webdriver
from selenium.webdriver.common.by import By


class RedoooHannoverSpider(Spider):
    name = "redooo-hannover"
    allowed_domains = ["redooo.de"]
    start_urls = ["https://www.redooo.de/privatkunden"]

    # PLZ für Hannover (Stadtzentrum)
    plz = "30159"

    # 9 Müllarten (Website-Name -> Standardisierter Name)
    waste_categories = [
        ("Baumischabfälle", "Baumischabfall"),
        ("Bauschutt", "Bauschutt"),
        ("Bauschutt (verunreinigt)", "Bauschutt verunreinigt"),
        ("Erdaushub (Boden und Steine)", "Boden"),
        ("Garten- und Parkabfälle", "Gartenabfälle"),
        ("Gemischte Metalle", "Metallschrott"),
        ("Holzabfälle (A1-A3)", "Holz A1-A3"),
        ("Holzabfälle (A4)", "Holz A4"),
        ("Sperrmüll", "Sperrmüll"),
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
        self.log(f"Starte Redooo Scraping (Hannover)")
        self.log(f"{'='*80}\n")

        total_products = 0

        # Setup: Go to start page, accept cookies, enter PLZ
        if not self._setup_session():
            self.log("❌ Session setup fehlgeschlagen")
            return

        # Für jede Abfallart
        for website_name, waste_type in self.waste_categories:
            self.log(f"\n--- Verarbeite: {waste_type} ---")

            try:
                # Use back navigation if we're on containerart
                if '/containerart' in self.driver.current_url:
                    self.driver.back()
                    sleep(3)

                # If not on abfallart, restart session
                if '/abfallart' not in self.driver.current_url:
                    self.log(f"  ⚠️ Nicht auf Abfallart-Seite, neu einrichten...")
                    self._setup_session()

                # Select waste type
                if not self._select_waste_type(website_name):
                    self.log(f"  ⚠️ Konnte {website_name} nicht auswählen")
                    continue

                sleep(1)

                # Click weiter to go to containerart
                if not self._click_weiter():
                    self.log(f"  ⚠️ Konnte nicht zu Container-Seite navigieren")
                    continue

                sleep(4)

                # Check if we're on containerart page
                if '/containerart' not in self.driver.current_url:
                    self.log(f"  ⚠️ Nicht auf Container-Seite")
                    continue

                # Extract container prices
                products = self._extract_containers(waste_type)

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

    def _setup_session(self):
        """Initialisiert Session mit Cookies und PLZ."""
        try:
            self.driver.get(self.start_urls[0])
            sleep(5)

            # Accept cookies
            self._accept_cookies()

            # Enter PLZ
            try:
                plz_input = self.driver.find_element(By.CSS_SELECTOR, "input[data-cy='location']")
                plz_input.clear()
                plz_input.send_keys(self.plz)
                sleep(2)

                # Select suggestion
                suggestions = self.driver.find_elements(By.CSS_SELECTOR, "a.dropdown-item")
                if suggestions:
                    for s in suggestions:
                        if s.text.strip():
                            self.driver.execute_script("arguments[0].click();", s)
                            break
                sleep(2)

                # Click weiter to go to abfallart
                self._click_weiter()
                sleep(3)

                self.log(f"  ✓ Session eingerichtet (PLZ: {self.plz})")
                return True

            except Exception as e:
                self.log(f"  ⚠️ PLZ-Eingabe Fehler: {e}")
                return False

        except Exception as e:
            self.log(f"  ⚠️ Session Setup Fehler: {e}")
            return False

    def _accept_cookies(self):
        """Akzeptiert Cookie-Banner."""
        try:
            buttons = self.driver.find_elements(By.TAG_NAME, "button")
            for btn in buttons:
                if 'akzeptieren' in (btn.text or '').lower():
                    self.driver.execute_script("arguments[0].click();", btn)
                    sleep(2)
                    return True
        except Exception:
            pass
        return False

    def _select_waste_type(self, waste_name):
        """Wählt eine Abfallart aus."""
        try:
            # Find element with exact text
            elements = self.driver.find_elements(By.XPATH, f"//*[text()='{waste_name}']")
            for elem in elements:
                if elem.is_displayed():
                    self.driver.execute_script("arguments[0].click();", elem)
                    return True
            return False
        except Exception as e:
            self.log(f"    ⚠️ Fehler bei Abfallart-Auswahl: {e}")
            return False

    def _click_weiter(self):
        """Klickt den 'weiter' Button."""
        try:
            weiter_elements = self.driver.find_elements(
                By.XPATH,
                "//span[contains(text(), 'weiter')] | //button[contains(text(), 'weiter')]"
            )
            for w in weiter_elements:
                if w.is_displayed():
                    self.driver.execute_script("arguments[0].click();", w)
                    return True
            return False
        except Exception:
            return False

    def _extract_containers(self, waste_type):
        """Extrahiert Container-Größen und Preise."""
        products = []
        seen_sizes = set()  # Deduplicate by size

        try:
            body = self.driver.find_element(By.TAG_NAME, "body")
            text = body.text
            lines = text.split('\n')

            for i, line in enumerate(lines):
                # Look for "X m³ Container" pattern
                size_match = re.match(r'(\d+)\s*m³\s*Container', line)
                if size_match and i + 1 < len(lines):
                    size = size_match.group(1)

                    # Skip BigBags (usually 1m³) and duplicates
                    if size == "1" or size in seen_sizes:
                        continue

                    # Next line should be price
                    price_line = lines[i + 1]
                    price_match = re.search(r'([\d.,]+)\s*€', price_line)
                    if price_match:
                        price = price_match.group(1)

                        # Remove thousand separator (1.234,00 -> 1234,00)
                        if '.' in price and ',' in price:
                            price = price.replace('.', '')

                        seen_sizes.add(size)

                        product = {
                            "source": "Redooo Hannover",
                            "title": f"{waste_type} {size} m³",
                            "type": waste_type,
                            "city": "Hannover",
                            "size": size,
                            "price": price,
                            "lid_price": "Plane oder Netz möglich",
                            "arrival_price": "inklusive",
                            "departure_price": "inklusive",
                            "max_rental_period": "21",
                            "fee_after_max": "1,00",
                            "cancellation_fee": None,
                            "URL": self.driver.current_url
                        }
                        products.append(product)

        except Exception as e:
            self.log(f"  ⚠️ Fehler bei Container-Extraktion: {e}")

        return products
