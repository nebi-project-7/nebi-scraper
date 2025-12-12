import logging
import re
from time import sleep

from scrapy import Spider
from scrapy.selector import Selector

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


class ElnoContainerProductsSpider(Spider):
    name = "elno-container-products"
    allowed_domains = ["heyflow.id"]

    # Alle bekannten Abfallarten basierend auf URL-Ankern
    # Format: (url-anker, Anzeigename)
    waste_types = [
        ("a1-a3-holz", "Holz A1-A3"),
        ("holz-a4-impraegniert", "Holz A4 (imprägniert)"),
        ("baumisch-leicht", "Baumisch (leicht)"),
        ("baumisch-20-mineralik", "Baumisch (20% Mineralik)"),
        ("bauschutt", "Bauschutt"),
        ("beton", "Beton"),
        ("boden-hell", "Boden (hell)"),
        ("boden-dunkel", "Boden (dunkel)"),
        ("gruenschnitt", "Grünschnitt"),
        ("gips", "Gips"),
        ("sperrmuell", "Sperrmüll"),
        ("siedlungsabfall", "Siedlungsabfall"),
        ("styropor", "Styropor"),
        ("kunststoff", "Kunststoff"),
        ("glas", "Glas"),
        ("dachpape", "Dachpappe"),
        ("daemwolle", "Dämmwolle"),
        ("asbest", "Asbest"),
        ("absetzzement", "Absetzzement"),
        ("elektronikschrott", "Elektronikschrott"),
        ("schrott", "Schrott"),
        ("pkwreifen", "PKW-Reifen"),
        ("wurzelnundstuben", "Wurzeln und Stubben"),
        ("fussbodenbelge", "Fußbodenbeläge"),
        ("verpackungsabfall", "Verpackungsabfall"),
    ]

    start_urls = ["https://heyflow.id/elno-container"]

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

        # Werte werden beim ersten Aufruf extrahiert
        self.rental_info = None

    def closed(self, reason):
        try:
            self.driver.quit()
        except Exception:
            pass

    def parse(self, response):
        self.log(f"\n{'='*80}")
        self.log(f"Starte Heyflow elno-container Scraping")
        self.log(f"{'='*80}\n")

        total_products = 0

        # Für jede Abfallart
        for url_anchor, display_name in self.waste_types:
            self.log(f"\n--- Verarbeite: {display_name} ---")

            url = f"https://heyflow.id/elno-container#abfallart-{url_anchor}"

            try:
                # Navigiere zur spezifischen Abfallart
                self.driver.get(url)
                sleep(7)  # Warten, bis Formular geladen ist

                # Extrahiere sichtbare Preise mit JavaScript
                products = self._extract_visible_products(display_name, url)

                if products:
                    self.log(f"  ✓ Gefunden: {len(products)} Container-Größen")
                    for product in products:
                        total_products += 1
                        yield product
                else:
                    self.log(f"  ⚠️ Keine Preise gefunden")

            except Exception as e:
                self.log(f"  ❌ Fehler: {e}")
                continue

        self.log(f"\n{'='*80}")
        self.log(f"✓ Gesamt gescrapt: {total_products} Produkte")
        self.log(f"{'='*80}\n")

    def _extract_rental_info(self):
        """
        Extrahiert Mietdauer und Zusatzgebühren von der Webseite.
        Wird nur einmal aufgerufen und dann gecached.
        """
        if self.rental_info is not None:
            return self.rental_info

        try:
            # Hole sichtbaren Text von der Seite
            visible_text = self.driver.execute_script("return document.body.innerText;")

            # Suche nach "14 Tage sind im Preis inbegriffen, jedeR weiterer Tag wird mit 3,-€"
            max_rental_period = "14"  # Default
            fee_after_max = ""  # Default leer

            # Pattern: "X Tage sind im Preis inbegriffen"
            rental_match = re.search(r'(\d+)\s+Tage?\s+sind\s+im\s+Preis', visible_text, re.IGNORECASE)
            if rental_match:
                max_rental_period = rental_match.group(1)

            # Pattern: "weiterer Tag wird mit X,-€" oder "weiterer Tag wird mit X€"
            fee_match = re.search(r'weiterer?\s+Tag.*?(\d+)[,.-]*\s*€', visible_text, re.IGNORECASE)
            if fee_match:
                fee_after_max = fee_match.group(1)

            self.rental_info = {
                "max_rental_period": max_rental_period,
                "fee_after_max": fee_after_max
            }

            self.log(f"✓ Mietinfo extrahiert: {max_rental_period} Tage, danach {fee_after_max}€/Tag")

        except Exception as e:
            self.log(f"⚠️ Fehler beim Extrahieren der Mietinfo: {e}")
            self.rental_info = {
                "max_rental_period": "14",
                "fee_after_max": ""
            }

        return self.rental_info

    def _extract_visible_products(self, waste_type: str, url: str) -> list:
        """
        Extrahiert nur die SICHTBAREN Preise mit JavaScript.
        Dies ist notwendig, weil der HTML-Code alle Abfallarten enthält,
        aber nur die ausgewählte Abfallart sichtbar ist.
        """
        products = []

        # Hole Mietinfo beim ersten Aufruf
        rental_info = self._extract_rental_info()

        # JavaScript Code, um nur sichtbare Preis-Elemente zu finden
        js_code = """
        var elements = document.querySelectorAll('p');
        var visiblePrices = [];

        elements.forEach(function(elem) {
            var text = elem.textContent || elem.innerText;
            if (text.includes('m³') && text.includes('Preis:')) {
                var style = window.getComputedStyle(elem);
                var isVisible = style.display !== 'none' &&
                               style.visibility !== 'hidden' &&
                               style.opacity !== '0' &&
                               elem.offsetHeight > 0;

                if (isVisible) {
                    // Extrahiere Größe und Preis
                    var sizeMatch = text.match(/(\\d+)\\s*m³/);
                    var priceMatch = text.match(/(\\d+[.,]\\d+)\\s*€/);
                    if (sizeMatch && priceMatch) {
                        visiblePrices.push({
                            size: sizeMatch[1],
                            price: priceMatch[1]
                        });
                    }
                }
            }
        });

        return visiblePrices;
        """

        try:
            visible_prices = self.driver.execute_script(js_code)

            for item in visible_prices:
                size = item['size']
                price = item['price']  # Behalte Komma als Dezimalzeichen

                product = {
                    "source": "elno-container.de",
                    "type": waste_type,
                    "city": "Berlin",
                    "size": size,
                    "price": price,
                    "lid_price": "",
                    "arrival_price": "inklusive",
                    "departure_price": "inklusive",
                    "max_rental_period": rental_info["max_rental_period"],
                    "fee_after_max": rental_info["fee_after_max"],
                    "cancellation_fee": "",
                    "URL": url
                }

                products.append(product)

            # Sortiere nach Größe
            products.sort(key=lambda x: int(x['size']))

        except Exception as e:
            self.log(f"⚠️ Fehler beim Extrahieren mit JavaScript: {e}")

        return products

    def _extract_products(self, html: str, waste_type: str, url: str) -> list:
        """
        Extrahiert alle Größe → Preis Kombinationen aus dem HTML.
        Sucht nach dem Abschnitt "Preise & Containergrößen" und extrahiert nur
        die Preise aus diesem aktiven Abschnitt.
        """
        products = []

        # Finde den Abschnitt nach "Preise & Containergrößen"
        # Dieser Abschnitt enthält die korrekten Preise für die ausgewählte Abfallart
        price_section_match = re.search(
            r'Preise\s*&(?:amp;)?\s*Containergr[oö]ßen(.*?)(?:Lieferzeit|Was darf|<div class="accordion"|$)',
            html,
            re.DOTALL | re.IGNORECASE
        )

        if not price_section_match:
            self.log(f"⚠️ Warnung: 'Preise & Containergrößen' Abschnitt nicht gefunden für {waste_type}")
            return products

        price_section = price_section_match.group(1)

        # Pattern: Xm³ ... Preis: Y.YY €
        pattern = r'(\d+)\s*m³.*?Preis:\s*(\d+[.,]\d+)\s*€'
        matches = re.findall(pattern, price_section, re.IGNORECASE | re.DOTALL)

        seen_sizes = set()

        for size, price in matches:
            # Bereinige Preis - behalte Komma als Dezimalzeichen
            price_clean = price

            # Vermeide Duplikate (gleiche Größe)
            if size in seen_sizes:
                continue
            seen_sizes.add(size)

            product = {
                "source": "elno-container.de",
                "type": waste_type,
                "city": "Berlin",
                "size": size,
                "price": price_clean,
                "lid_price": "kostenlos wenn verfügbar",
                "arrival_price": "inklusive",
                "departure_price": "inklusive",
                "max_rental_period": "14",
                "fee_after_max": "siehe AGB",
                "cancellation_fee": "siehe AGB",
                "URL": url
            }

            products.append(product)

        # Sortiere nach Größe
        products.sort(key=lambda x: int(x['size']))

        return products
