import re
import logging
from time import sleep
from scrapy import Spider
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from scrapy.selector import Selector


class BerlinRecyclingSpider(Spider):
    name = 'berlin-recycling'
    allowed_domains = ['shop.berlin-recycling.de']
    start_urls = ['https://shop.berlin-recycling.de/']

    # Direkte Produkt-URLs für alle Abfallarten
    PRODUCT_URLS = [
        "https://shop.berlin-recycling.de/products/baumischabfall-entsorgen-container",
        "https://shop.berlin-recycling.de/products/bauschutt-entsorgen-container",
        "https://shop.berlin-recycling.de/products/erdaushub-entsorgen-container",
        "https://shop.berlin-recycling.de/products/asbestentsorgung-container",
        "https://shop.berlin-recycling.de/products/elektrogrossgerate-container",
        "https://shop.berlin-recycling.de/products/elektrokleingeraete-container",
        "https://shop.berlin-recycling.de/products/gartenabfall-entsorgen-container",
        "https://shop.berlin-recycling.de/products/gemischte-verpackungen-entsorgen-container",
        "https://shop.berlin-recycling.de/products/gewerbeabfall-entsorgen-container",
        "https://shop.berlin-recycling.de/products/glaswolle-entsorgung-container",
        "https://shop.berlin-recycling.de/products/holz-a1-entsorgen-container",
        "https://shop.berlin-recycling.de/products/holz-a2-a3-entsorgen-container",
        "https://shop.berlin-recycling.de/products/holz-a4-entsorgen-container",
        "https://shop.berlin-recycling.de/products/pappe-papier-entsorgen-container",
        "https://shop.berlin-recycling.de/products/rigipsentsorgung-container",
        "https://shop.berlin-recycling.de/products/sperrmuell-entsorgen-container",
        "https://shop.berlin-recycling.de/products/styropor-eps-entsorgung-container",
        "https://shop.berlin-recycling.de/products/verpackungsstyropor-entsorgung-container",
    ]

    def __init__(self):
        logging.getLogger('selenium').setLevel(logging.WARNING)
        logging.getLogger('urllib3').setLevel(logging.WARNING)

        options = webdriver.ChromeOptions()
        options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.add_argument('--window-size=1920,1080')
        self.driver = webdriver.Chrome(options=options)
        self.cookie_dismissed = False
        # Set zur Vermeidung von Duplikaten (type + size Kombination)
        self.seen_products = set()

    def _dismiss_cookie_banner(self):
        """Schließt Cookie-Banner."""
        if self.cookie_dismissed:
            return

        cookie_selectors = [
            "//button[@title='Akzeptieren Sie alle cookies']",
            "//button[contains(text(), 'Alle akzeptieren')]",
            "//button[@id='onetrust-accept-btn-handler']",
        ]

        for selector in cookie_selectors:
            try:
                element = WebDriverWait(self.driver, 3).until(
                    EC.element_to_be_clickable((By.XPATH, selector))
                )
                self.driver.execute_script("arguments[0].click();", element)
                self.log("Cookie-Banner geschlossen")
                self.cookie_dismissed = True
                sleep(1)
                return
            except:
                pass

    def _js_click(self, element):
        """JavaScript-Klick für robustere Interaktion."""
        self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
        sleep(0.3)
        self.driver.execute_script("arguments[0].click();", element)

    def _extract_price(self):
        """Extrahiert den aktuellen Preis von der Seite.

        Returns tuple: (price, is_tonnage_price)
        - is_tonnage_price=True wenn es ein Basis-Preis pro Tonnage ist
        """
        try:
            page_text = self.driver.execute_script("return document.body.innerText;")

            # Prüfe ob es ein Tonnage-Preis ist (Abrollcontainer)
            is_tonnage = 'pro Tonnage' in page_text or 'Tonnage zzgl' in page_text

            if is_tonnage:
                # Bei Tonnage-Preisen: Finde den ersten großen Preis (Basis-Transportpreis)
                prices = re.findall(r'(\d{1,3}(?:\.\d{3})*,\d{2})\s*€', page_text)
                for price in prices:
                    price_float = float(price.replace('.', '').replace(',', '.'))
                    if price_float >= 200:  # Basis-Preis typischerweise >= 200€
                        return (price, True)
            else:
                # Bei Pauschalpreisen: Suche nach "Nettopreis" Kontext
                nettopreis_match = re.search(r'(\d{1,3}(?:\.\d{3})*,\d{2})\s*€\s*Nettopreis', page_text)
                if nettopreis_match:
                    return (nettopreis_match.group(1), False)

                # Fallback: Erstes Vorkommen von XXX,XX €
                prices = re.findall(r'(\d{1,3}(?:\.\d{3})*,\d{2})\s*€', page_text)
                for price in prices:
                    price_float = float(price.replace('.', '').replace(',', '.'))
                    if price_float > 200:
                        return (price, False)
        except:
            pass
        return (None, False)

    def _extract_fee_after_max(self):
        """Extrahiert die Gebühr nach Mietdauer."""
        try:
            page_text = self.driver.execute_script("return document.body.innerText;")
            # Pattern: "danach X,XX € netto" oder "X,XX € netto zzgl."
            fee_match = re.search(r'danach\s+(\d+,\d{2})\s*€\s*netto', page_text, re.IGNORECASE)
            if fee_match:
                return fee_match.group(1) + '€'
        except:
            pass
        return ""

    def _extract_max_rental(self):
        """Extrahiert die maximale Mietdauer."""
        try:
            page_text = self.driver.execute_script("return document.body.innerText;")
            # Pattern: "bis zu X Tage" oder "X Tage Miete"
            rental_match = re.search(r'bis\s+(?:zu\s+)?(\d+)\s+Tage', page_text, re.IGNORECASE)
            if rental_match:
                return rental_match.group(1)
        except:
            pass
        return "10"  # Default

    def closed(self, reason):
        try:
            self.driver.quit()
        except:
            pass

    def parse(self, response):
        for product_url in self.PRODUCT_URLS:
            self.log(f"Verarbeite: {product_url}")

            try:
                self.driver.get(product_url)
                sleep(4)

                # Cookie-Banner schließen
                self._dismiss_cookie_banner()

                # Titel extrahieren (= Abfallart)
                try:
                    title = self.driver.find_element(By.XPATH, "//h1").text
                    # Entferne "(Container)" aus dem Titel
                    waste_type = title.replace('(Container)', '').replace('Container', '').strip()
                    # Umbenennungen
                    if waste_type == 'Gartenabfall':
                        waste_type = 'Gartenabfälle'
                    elif waste_type == 'Gewerbeabfall':
                        waste_type = 'Gewerbeabfälle'
                except:
                    self.log(f"Titel nicht gefunden für {product_url}")
                    continue

                # Finde das Dropdown für Containergrößen
                try:
                    size_select_element = self.driver.find_element(
                        By.XPATH,
                        "//select[.//option[contains(text(), 'm³')]]"
                    )
                    size_select = Select(size_select_element)
                    size_options = [opt for opt in size_select.options
                                    if 'm³' in opt.text and opt.get_attribute('disabled') is None]
                except Exception as e:
                    self.log(f"Größen-Dropdown nicht gefunden für {waste_type}: {e}")
                    continue

                self.log(f"  Gefunden: {len(size_options)} Größen für {waste_type}")

                # Für jede Containergröße
                for i, size_option in enumerate(size_options):
                    try:
                        size_text = size_option.text  # z.B. "3 m³ Muldencontainer"

                        # Extrahiere Größe (z.B. "3" aus "3 m³ Muldencontainer")
                        size_match = re.search(r'(\d+(?:,\d+)?)\s*m³', size_text)
                        if not size_match:
                            continue
                        size = size_match.group(1)

                        # Wähle diese Option über Select-Klasse
                        size_select.select_by_index(i)
                        sleep(3)  # Längere Wartezeit für JavaScript-Updates

                        # Extrahiere Preis (returns tuple: price, is_tonnage)
                        price, is_tonnage = self._extract_price()
                        if not price:
                            self.log(f"    Kein Preis für {size} m³")
                            continue

                        # Extrahiere weitere Infos
                        fee_after_max = self._extract_fee_after_max()
                        max_rental_period = self._extract_max_rental()

                        # Bei Tonnage-Preisen: markiere als Basis-Preis
                        price_note = ""
                        if is_tonnage:
                            price_note = " (Basis + Tonnage)"

                        item = {
                            'source': 'berlin-recycling.de',
                            'title': f"{size} m³ {waste_type}",
                            'type': waste_type,
                            'city': 'Berlin',
                            'size': size,
                            'price': price,
                            'lid_price': '',
                            'arrival_price': 'inklusive',
                            'departure_price': 'inklusive',
                            'max_rental_period': max_rental_period,
                            'fee_after_max': fee_after_max,
                            'cancellation_fee': '',
                            'URL': self.driver.current_url
                        }

                        # Duplikat-Check: type + size Kombination
                        product_key = f"{waste_type}|{size}"
                        if product_key not in self.seen_products:
                            self.seen_products.add(product_key)
                            self.log(f"    {size} m³: {price} €{price_note}")
                            yield item
                        else:
                            self.log(f"    ⚠️ Duplikat übersprungen: {waste_type} {size} m³")

                    except Exception as e:
                        self.log(f"    Fehler bei Größe: {e}")
                        continue

            except Exception as e:
                self.log(f"Fehler bei {product_url}: {e}")
                continue
