"""
Dinkel GmbH Spider
Extrahiert Preise für Container-Entsorgung in Stuttgart
Shop: https://shop.dinkel-gmbh.de/
"""

import logging
import re
from time import sleep

from scrapy import Spider

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import TimeoutException
from webdriver_manager.chrome import ChromeDriverManager


class DinkelGmbHSpider(Spider):
    name = "dinkel-gmbh"
    allowed_domains = ["shop.dinkel-gmbh.de"]
    start_urls = ["https://shop.dinkel-gmbh.de/"]

    # PLZ für Stuttgart
    PLZ = "70191"

    # Mapping von Website-Namen zu standardisierten Abfalltypen
    waste_type_mapping = {
        'mischpapier': 'Papier/Pappe',
        'b12': 'Papier/Pappe',
        'bauschutt': 'Bauschutt',
        'baustellenmischabfälle': 'Baumischabfall',
        'baustellenmischabfall': 'Baumischabfall',
        'sperrmüll': 'Sperrmüll',
        'grünschnitt': 'Gartenabfälle',
        'gartenabfälle': 'Gartenabfälle',
        'gartenabfall': 'Gartenabfälle',
        'mischholz': 'Holz A1-A3',
        'holz a1': 'Holz A1-A3',
        'erdaushub': 'Erdaushub',
        'sand': 'Sand',
    }

    # Abfalltypen bei denen NUR Absetzmulde erlaubt ist (keine Deckelmulde)
    ONLY_ABSETZMULDE = [
        'Papier/Pappe',
        'Baumischabfall',
        'Holz A1-A3',
        'Sperrmüll',
    ]

    # Artikel die übersprungen werden sollen
    SKIP_ARTICLES = [
        'dinkel sack',
        'dinkelsack',
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

        service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=options)
        self.seen_products = set()

    def closed(self, reason):
        try:
            self.driver.quit()
        except Exception:
            pass

    def _js_click(self, element):
        """JavaScript-Klick für zuverlässigere Interaktion."""
        self.driver.execute_script("arguments[0].click();", element)

    def parse(self, response):
        self.log(f"\n{'='*80}")
        self.log(f"Starte Dinkel GmbH Scraping für Stuttgart")
        self.log(f"{'='*80}\n")

        total_products = 0

        try:
            # 1. Startseite laden
            self.driver.get(self.start_urls[0])
            sleep(3)

            # Cookie-Banner schließen
            self._dismiss_cookie_banner()

            # 2. PLZ eingeben
            if not self._enter_plz():
                self.log("FEHLER: Konnte PLZ nicht eingeben")
                return

            # 3. Zur Artikelseite navigieren
            self.driver.get("https://shop.dinkel-gmbh.de/order/article/index")
            sleep(5)  # Warte auf dynamisches Laden

            self.log(f"Artikelseite geladen: {self.driver.current_url}")

            # 4. Alle Artikel sammeln
            articles = self._get_articles()
            self.log(f"Gefundene Artikel: {len(articles)}")

            # 5. Jeden Artikel verarbeiten
            for article_name in articles:
                if self._should_skip(article_name):
                    self.log(f"  Überspringe: {article_name}")
                    continue

                self.log(f"\n--- Verarbeite: {article_name} ---")

                # Zur Artikelseite (frisch laden für jeden Artikel)
                self.driver.get("https://shop.dinkel-gmbh.de/order/article/index")
                sleep(3)

                # Artikel auswählen
                if not self._select_article(article_name):
                    self.log(f"  FEHLER: Konnte {article_name} nicht auswählen")
                    continue

                sleep(3)
                self.log(f"  URL nach Auswahl: {self.driver.current_url}")

                # Container-Optionen extrahieren
                waste_type = self._map_waste_type(article_name)
                products = self._extract_containers(waste_type)

                for product in products:
                    # Verwende Titel als Key um Absetzmulde/Deckelmulde zu unterscheiden
                    product_key = product['title']
                    if product_key not in self.seen_products:
                        self.seen_products.add(product_key)
                        total_products += 1
                        self.log(f"  ✓ {product['size']}: {product['price']} EUR")
                        yield product

        except Exception as e:
            self.log(f"FEHLER: {e}")
            import traceback
            self.log(traceback.format_exc())

        self.log(f"\n{'='*80}")
        self.log(f"Gesamt gescrapt: {total_products} Produkte")
        self.log(f"{'='*80}\n")

    def _dismiss_cookie_banner(self):
        """Schließt Cookie-Banner."""
        try:
            cookie_btn = self.driver.find_element(By.CSS_SELECTOR, ".btn-cookie-close")
            self._js_click(cookie_btn)
            self.log("Cookie-Banner geschlossen")
            sleep(1)
        except:
            pass

    def _enter_plz(self):
        """Gibt PLZ ein und bestätigt."""
        try:
            # PLZ-Feld finden
            plz_input = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.ID, "postcode"))
            )

            # PLZ eingeben (langsam für Autocomplete)
            for char in self.PLZ:
                plz_input.send_keys(char)
                sleep(0.1)

            self.log(f"PLZ {self.PLZ} eingegeben")
            sleep(2)

            # Autocomplete-Vorschlag wählen
            try:
                suggestions = WebDriverWait(self.driver, 5).until(
                    EC.presence_of_all_elements_located((By.CSS_SELECTOR, ".autocomplete-suggestion"))
                )
                if suggestions:
                    self.log(f"Wähle: {suggestions[0].text}")
                    self._js_click(suggestions[0])
                    sleep(1)
            except:
                pass

            # Los-Button klicken
            submit_btn = self.driver.find_element(By.CSS_SELECTOR, "button.btn-primary[type='submit']")
            self._js_click(submit_btn)
            self.log("PLZ bestätigt")
            sleep(3)

            return "/order/" in self.driver.current_url

        except Exception as e:
            self.log(f"PLZ-Eingabe Fehler: {e}")
            return False

    def _get_articles(self):
        """Sammelt alle Artikelnamen von der Seite."""
        articles = []
        try:
            # Artikel sind in .item Elementen, Titel in h3.info-btn-wrapper
            items = self.driver.find_elements(By.CSS_SELECTOR, ".item")
            for item in items:
                try:
                    title = item.find_element(By.CSS_SELECTOR, "h3.info-btn-wrapper, h3, .card-title")
                    name = title.text.strip()
                    if name:
                        articles.append(name)
                except:
                    continue
        except Exception as e:
            self.log(f"Fehler beim Sammeln der Artikel: {e}")
        return articles

    def _should_skip(self, article_name):
        """Prüft ob Artikel übersprungen werden soll."""
        name_lower = article_name.lower()
        for skip in self.SKIP_ARTICLES:
            if skip in name_lower:
                return True
        return False

    def _select_article(self, article_name):
        """Wählt einen Artikel durch Klicken auf den Auswählen-Button."""
        try:
            items = self.driver.find_elements(By.CSS_SELECTOR, ".item")
            for item in items:
                try:
                    title = item.find_element(By.CSS_SELECTOR, "h3.info-btn-wrapper, h3")
                    title_text = title.text
                    # Überspringe DINKEL SACK Artikel
                    if "DINKEL" in title_text.upper():
                        continue
                    if article_name in title_text:
                        # Finde den Auswählen-Button in diesem Item
                        btn = item.find_element(By.CSS_SELECTOR, "button[name='Article_Add']")
                        self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn)
                        sleep(0.5)
                        self._js_click(btn)
                        return True
                except:
                    continue
            return False
        except Exception as e:
            self.log(f"Artikel-Auswahl Fehler: {e}")
            return False

    def _extract_containers(self, waste_type):
        """Extrahiert Container-Größen und Preise."""
        products = []

        # Prüfe ob nur Absetzmulde erlaubt ist
        only_absetzmulde = waste_type in self.ONLY_ABSETZMULDE

        try:
            # Container sind in .container-size Elementen
            containers = self.driver.find_elements(By.CSS_SELECTOR, ".container-size, a.card[onclick*='container.select']")

            self.log(f"  Container-Elemente gefunden: {len(containers)}")

            for container in containers:
                try:
                    # Titel extrahieren (z.B. "7 cbm Absetzmulde")
                    try:
                        title_elem = container.find_element(By.CSS_SELECTOR, "p.title, .title")
                        title = title_elem.text.strip()
                    except:
                        title = container.text.strip()

                    # Größe extrahieren
                    size_match = re.search(r'(\d+)\s*cbm', title, re.IGNORECASE)
                    if not size_match:
                        continue

                    size = f"{size_match.group(1)} m³"

                    # Container-Typ
                    container_type = ""
                    is_deckelmulde = "deckelmulde" in title.lower()
                    if is_deckelmulde:
                        container_type = " Deckelmulde"
                    elif "absetzmulde" in title.lower():
                        container_type = " Absetzmulde"

                    # Überspringe Deckelmulde wenn nur Absetzmulde erlaubt
                    if only_absetzmulde and is_deckelmulde:
                        self.log(f"  Überspringe Deckelmulde für {waste_type}")
                        continue

                    # Preis extrahieren
                    try:
                        price_elem = container.find_element(By.CSS_SELECTOR, "p.price, .price")
                        price_text = price_elem.text.strip()
                    except:
                        price_text = container.text.strip()

                    # Preis mit optionalem Tausendertrennzeichen (z.B. "1.095,00 EUR")
                    price_match = re.search(r'(\d{1,3}(?:\.\d{3})*(?:,\d{2})?)\s*EUR', price_text, re.IGNORECASE)
                    if not price_match:
                        # Fallback ohne Tausendertrennzeichen
                        price_match = re.search(r'(\d+(?:,\d{2})?)\s*EUR', price_text, re.IGNORECASE)
                    if not price_match:
                        continue

                    # Entferne Tausendertrennzeichen und füge "ab " hinzu
                    price_value = price_match.group(1).replace('.', '')
                    price = f"ab {price_value}"

                    # Produkt erstellen
                    product = {
                        "source": "Dinkel GmbH",
                        "title": f"{size}{container_type} {waste_type}",
                        "type": waste_type,
                        "city": "Stuttgart",
                        "size": size,
                        "price": price,
                        "lid_price": None if "Absetzmulde" in container_type else "inklusive",
                        "arrival_price": "inklusive",
                        "departure_price": "inklusive",
                        "max_rental_period": "3 Tage",
                        "fee_after_max": "2,00 EUR/Tag",
                        "cancellation_fee": None,
                        "URL": self.driver.current_url
                    }

                    # Duplikate vermeiden
                    key = f"{size}|{container_type}"
                    if key not in [p.get('_key') for p in products]:
                        product['_key'] = key
                        products.append(product)

                except Exception as e:
                    self.log(f"  Container-Element Fehler: {e}")
                    continue

        except Exception as e:
            self.log(f"Container-Extraktion Fehler: {e}")

        # Entferne temporäre Keys
        for p in products:
            p.pop('_key', None)

        return products

    def _map_waste_type(self, article_name):
        """Mappt Artikelname auf standardisierten Abfalltyp."""
        name_lower = article_name.lower()

        # Spezielle Fälle
        if 'mischpapier' in name_lower or 'b12' in name_lower:
            return 'Papier/Pappe'

        # Mapping durchsuchen
        for key, value in self.waste_type_mapping.items():
            if key in name_lower:
                return value

        # Fallback: Original-Namen bereinigen
        # Entferne "- mineralisch ohne Störstoffe" etc.
        clean_name = article_name.split('-')[0].strip()
        return clean_name
