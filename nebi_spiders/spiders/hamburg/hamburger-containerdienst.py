"""
Hamburger Containerdienst Spider
Extrahiert Preise für Container-Entsorgung in Hamburg
Shop: https://www.hamburger-containerdienst.de/containerpreise/
"""

import logging
import re
from time import sleep

from scrapy import Spider

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.common.exceptions import StaleElementReferenceException


class HamburgerContainerdienstSpider(Spider):
    name = "hamburger-containerdienst"
    allowed_domains = ["hamburger-containerdienst.de"]
    start_urls = ["https://www.hamburger-containerdienst.de/containerpreise/"]

    # Kategorien: (Text auf Website enthält, standardisierter Name, Ausschlusstexte)
    waste_categories = [
        (">Bauschutt</strong>", "Bauschutt", ["ohne", "mit", "Dachziegel"]),  # Exakt "Bauschutt"
        ("ohne</strong> Bauschutt", "Baumischabfall", []),  # Baustellenabfall ohne Bauschutt
        ("Baustellenabfall mit Bauschutt", "Baumischabfall mit Bauschutt", []),
        ("Sperrmüll</strong>", "Sperrmüll", []),
        ("Gartenabfall</strong>", "Gartenabfälle", []),  # Immer "Gartenabfälle"
        ("Gipsabfall</strong>", "Gips", []),
        ("Holz A1", "Holz A1-A3", ["A4"]),
        ("Holz A4", "Holz A4", []),
        (">Beton</strong>", "Beton", []),
        ("Dachziegel", "Dachziegel", []),
        ("Boden mit Bauschutt", "Boden", []),  # Boden mit Bauschutt ist verfügbar
        ("KMF-Wolle", "Dämmstoffe", []),
        ("Teer- und bitumhaltige", "Dachpappe", []),
        ("Gewerbeabfall</strong>", "Gewerbeabfall", []),
        ("Mutterboden / Oberboden", "Mutterboden", ["Grassoden"]),
    ]

    # Container-Größen zum Testen
    container_sizes = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 12, 15, 18, 20]

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
        self.transport_price = "172,55"
        self.stellzeit = "7"

    def closed(self, reason):
        try:
            self.driver.quit()
        except Exception:
            pass

    def parse(self, response):
        self.log(f"\n{'='*80}")
        self.log(f"Starte Hamburger Containerdienst Scraping")
        self.log(f"{'='*80}\n")

        total_products = 0

        try:
            # Lade Hauptseite
            self.driver.get(self.start_urls[0])
            sleep(3)

            # Cookie-Banner schließen
            self._dismiss_cookie_banner()

            # Extrahiere Transport-Kosten und Stellzeit
            self._extract_fixed_info()

            # Für jede Abfallart
            for search_text, waste_type, exclude_texts in self.waste_categories:
                self.log(f"\n--- Verarbeite: {waste_type} ---")

                try:
                    # Wähle Abfallart aus
                    if not self._select_waste_type(search_text, exclude_texts):
                        self.log(f"  ⚠️ Konnte {waste_type} nicht auswählen")
                        continue

                    sleep(1)

                    # Für jede Container-Größe
                    for size in self.container_sizes:
                        try:
                            # Wähle Größe aus
                            if not self._select_container_size(size):
                                continue

                            sleep(0.5)

                            # Prüfe ob Container verfügbar
                            if self._is_not_available():
                                continue

                            # Extrahiere Preis
                            price = self._extract_price()
                            if not price or price == "-":
                                continue

                            # Duplikat-Check
                            product_key = f"{waste_type}|{size}"
                            if product_key in self.seen_products:
                                continue
                            self.seen_products.add(product_key)

                            total_products += 1
                            self.log(f"  ✓ {size}m³: {price}€")

                            yield {
                                "source": "Hamburger Containerdienst",
                                "title": f"{waste_type} {size} m³",
                                "type": waste_type,
                                "city": "Hamburg",
                                "size": str(size),
                                "price": price,
                                "lid_price": None,
                                "arrival_price": self.transport_price,
                                "departure_price": "inklusive",
                                "max_rental_period": self.stellzeit,
                                "fee_after_max": None,
                                "cancellation_fee": None,
                                "URL": self.start_urls[0]
                            }

                        except StaleElementReferenceException:
                            # Element wurde aktualisiert, weiter mit nächster Größe
                            continue
                        except Exception as e:
                            self.log(f"  ⚠️ Fehler bei {size}m³: {e}")
                            continue

                except Exception as e:
                    self.log(f"  ❌ Fehler bei {waste_type}: {e}")
                    continue

        except Exception as e:
            self.log(f"❌ Allgemeiner Fehler: {e}")

        self.log(f"\n{'='*80}")
        self.log(f"✓ Gesamt gescrapt: {total_products} Produkte")
        self.log(f"{'='*80}\n")

    def _dismiss_cookie_banner(self):
        """Schließt Cookie-Banner."""
        try:
            # Klicke auf Cookie-Control Button
            cookie_btn = self.driver.find_element(By.CSS_SELECTOR, "button.ccm--ctrl-init")
            self.driver.execute_script("arguments[0].click();", cookie_btn)
            sleep(1)

            # Klicke auf "Alle akzeptieren"
            accept_btns = self.driver.find_elements(
                By.XPATH,
                "//button[contains(text(), 'Alle akzeptieren') or contains(text(), 'Akzeptieren')]"
            )
            for btn in accept_btns:
                try:
                    self.driver.execute_script("arguments[0].click();", btn)
                    sleep(1)
                    return
                except:
                    pass
        except:
            pass

    def _extract_fixed_info(self):
        """Extrahiert Transport-Kosten und Stellzeit von der Seite."""
        try:
            page_source = self.driver.page_source

            # Transport-Kosten extrahieren (Brutto - vor "EUR" und vor "Netto")
            # Format: "172,55 EUR (145,00 EUR Netto...)"
            transport_match = re.search(r'(\d+[,\.]\d{2})\s*EUR\s*\(\d+[,\.]\d{2}\s*EUR\s*Netto', page_source)
            if transport_match:
                self.transport_price = transport_match.group(1).replace('.', ',')
                self.log(f"  Transport-Kosten (Brutto): {self.transport_price}€")

            # Stellzeit extrahieren
            stellzeit_match = re.search(r'(\d+)\s*Tage\s*Stellzeit', page_source, re.IGNORECASE)
            if stellzeit_match:
                self.stellzeit = stellzeit_match.group(1)
                self.log(f"  Stellzeit: {self.stellzeit} Tage")

        except Exception as e:
            self.log(f"  ⚠️ Fehler beim Extrahieren der festen Infos: {e}")

    def _select_waste_type(self, search_text, exclude_texts):
        """Wählt eine Abfallart aus dem Menü."""
        try:
            # Hole alle Abfallart-Optionen frisch
            selectables = self.driver.find_elements(By.CSS_SELECTOR, ".selectable")
            if not selectables:
                return False

            waste_selector = selectables[0]
            waste_options = waste_selector.find_elements(By.XPATH, "./div[@data-category]")

            for opt in waste_options:
                try:
                    html = opt.get_attribute('innerHTML')
                    if not html:
                        continue

                    # Prüfe ob Suchtext enthalten
                    if search_text not in html:
                        continue

                    # Prüfe Ausschlusstexte
                    excluded = False
                    for exclude in exclude_texts:
                        if exclude.lower() in html.lower():
                            excluded = True
                            break

                    if excluded:
                        continue

                    # Gefunden - klicken
                    self.driver.execute_script("arguments[0].click();", opt)
                    return True

                except StaleElementReferenceException:
                    continue

            return False

        except Exception as e:
            self.log(f"    ⚠️ Fehler bei Abfallart-Auswahl: {e}")
            return False

    def _select_container_size(self, size):
        """Wählt eine Container-Größe aus dem Dropdown."""
        try:
            # Hole Größen-Optionen frisch
            selectables = self.driver.find_elements(By.CSS_SELECTOR, ".selectable")
            if len(selectables) < 2:
                return False

            size_selector = selectables[1]
            size_options = size_selector.find_elements(By.XPATH, "./div")

            for opt in size_options:
                try:
                    html = opt.get_attribute('innerHTML')
                    if not html:
                        continue

                    # Suche nach exakter Größe
                    if f'<strong>{size}</strong>' in html:
                        self.driver.execute_script("arguments[0].click();", opt)
                        return True

                except StaleElementReferenceException:
                    continue

            return False

        except Exception as e:
            return False

    def _is_not_available(self):
        """Prüft ob Container nicht verfügbar ist."""
        try:
            page_source = self.driver.page_source
            # Prüfe auf "nicht in unserem Sortiment" Nachricht
            if "nicht in unserem Sortiment" in page_source:
                return True
            if "befindet sich nicht" in page_source:
                return True
            return False
        except:
            return False

    def _extract_price(self):
        """Extrahiert den aktuellen Preis."""
        try:
            # Suche nach Preis-Element
            price_elem = self.driver.find_element(By.CSS_SELECTOR, "span.price")
            price_text = price_elem.text.strip()

            # Prüfe auf Platzhalter
            if price_text == "-" or price_text == "–" or not price_text:
                return None

            # Bereinige Preis (entferne "EUR" etc.)
            price_clean = re.sub(r'[^\d,\.]', '', price_text)
            if price_clean:
                return price_clean.replace('.', ',')

            return None

        except Exception as e:
            return None
