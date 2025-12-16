"""
DIBA Entsorgung Spider
Extrahiert Preise für Container-Entsorgung in Hannover
Shop: https://www.diba-entsorgung.de/shop
"""

import logging
import re
from time import sleep

from scrapy import Spider

from selenium import webdriver
from selenium.webdriver.common.by import By


class DibaEntsorgungSpider(Spider):
    name = "diba-entsorgung"
    allowed_domains = ["diba-entsorgung.de"]
    start_urls = ["https://www.diba-entsorgung.de/shop"]

    # 6 Abfallarten (URL-Pfad -> Standardisierter Name)
    # Ignoriere: Mülltasche/Big Bag
    waste_categories = [
        ("01-03-2025-sperrm%C3%BCll-container", "Sperrmüll"),
        ("kopie-von-buschwerk-und-gartenabfall-container", "Gartenabfälle"),
        ("01-03-2025-alt-und-bauholz-behandelt-aii-aiii-container", "Holz A2-A3"),
        ("01-03-2025-baustellenmischabfall-container", "Baumischabfall"),
        ("01-03-2025-boden-container", "Boden"),
        ("01-03-2025-bauschutt-container", "Bauschutt"),
    ]

    # Container-Größen (ohne BigBag)
    container_sizes = ["5 cbm", "7 cbm", "10 cbm", "19 cbm", "36 cbm"]

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
        self.cookies_accepted = False

    def closed(self, reason):
        try:
            self.driver.quit()
        except Exception:
            pass

    def parse(self, response):
        self.log(f"\n{'='*80}")
        self.log(f"Starte DIBA Entsorgung Scraping (Hannover)")
        self.log(f"{'='*80}\n")

        total_products = 0

        # Für jede Abfallart
        for url_slug, waste_type in self.waste_categories:
            self.log(f"\n--- Verarbeite: {waste_type} ---")

            try:
                # Für jede Größe
                for size_text in self.container_sizes:
                    try:
                        # Zur Produktseite navigieren
                        url = f"https://www.diba-entsorgung.de/product-page/{url_slug}"
                        self.driver.get(url)
                        sleep(3)

                        # Cookie-Banner akzeptieren (nur einmal)
                        if not self.cookies_accepted:
                            self._accept_cookies()
                            self.cookies_accepted = True

                        # Dropdown öffnen
                        if not self._open_dropdown():
                            continue

                        # Größe auswählen
                        if not self._select_size(size_text):
                            continue

                        sleep(1.5)

                        # Preis extrahieren
                        price = self._extract_price()
                        if not price:
                            continue

                        # Größe als Zahl extrahieren
                        size = size_text.replace(" cbm", "")

                        product_key = f"{waste_type}|{size}"
                        if product_key not in self.seen_products:
                            self.seen_products.add(product_key)
                            total_products += 1

                            product = {
                                "source": "DIBA Entsorgung",
                                "title": f"{waste_type} {size} m³",
                                "type": waste_type,
                                "city": "Hannover",
                                "size": size,
                                "price": price,
                                "lid_price": None,
                                "arrival_price": "inklusive",
                                "departure_price": "inklusive",
                                "max_rental_period": "7",
                                "fee_after_max": "2,50",
                                "cancellation_fee": None,
                                "URL": url
                            }

                            self.log(f"  ✓ {size}m³: {price}€")
                            yield product

                    except Exception as e:
                        self.log(f"  ⚠️ Fehler bei {size_text}: {e}")
                        continue

            except Exception as e:
                self.log(f"  ❌ Fehler bei {waste_type}: {e}")
                continue

        self.log(f"\n{'='*80}")
        self.log(f"✓ Gesamt gescrapt: {total_products} Produkte")
        self.log(f"{'='*80}\n")

    def _accept_cookies(self):
        """Akzeptiert Cookie-Banner falls vorhanden."""
        try:
            cookie_btns = self.driver.find_elements(
                By.XPATH,
                "//button[contains(text(), 'Zustimmen')] | //button[contains(text(), 'Akzeptieren')]"
            )
            for btn in cookie_btns:
                if btn.is_displayed():
                    self.driver.execute_script("arguments[0].click();", btn)
                    sleep(1)
                    return True
        except Exception:
            pass
        return False

    def _open_dropdown(self):
        """Öffnet das Größen-Dropdown."""
        try:
            dropdown_elem = self.driver.find_element(
                By.XPATH,
                "//*[contains(text(), 'Auswählen')]"
            )
            if dropdown_elem.is_displayed():
                self.driver.execute_script("arguments[0].click();", dropdown_elem)
                sleep(1)
                return True
        except Exception:
            pass
        return False

    def _select_size(self, size_text):
        """Wählt eine Größe aus dem Dropdown."""
        try:
            options = self.driver.find_elements(
                By.XPATH,
                f"//*[contains(text(), '{size_text}')]"
            )
            for opt in options:
                if opt.is_displayed() and 'cbm' in opt.text:
                    self.driver.execute_script("arguments[0].click();", opt)
                    return True
        except Exception:
            pass
        return False

    def _extract_price(self):
        """Extrahiert den aktuellen Preis."""
        try:
            body = self.driver.find_element(By.TAG_NAME, "body")
            text = body.text
            lines = text.split('\n')

            for line in lines:
                # Preis-Zeile finden (nicht Big Bag Preis von 10,00 €)
                line = line.strip()
                price_match = re.match(r'^(\d+[.,]\d{2})\s*€', line)
                if price_match:
                    price = price_match.group(1)
                    # Plausibilitätscheck (> 50€)
                    try:
                        price_val = float(price.replace(',', '.'))
                        if price_val > 50:
                            return price
                    except ValueError:
                        pass

        except Exception:
            pass
        return None
