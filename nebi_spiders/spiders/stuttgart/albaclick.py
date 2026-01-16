"""
Alba Click Spider für Stuttgart
Extrahiert Preise für Container-Entsorgung in Stuttgart
Website: https://shop.albaclick.de/
"""

import re
import logging
from time import sleep
from scrapy import Spider
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from scrapy.selector import Selector


class AlbaclickStuttgartSpider(Spider):
    name = 'albaclick-stuttgart'
    allowed_domains = ['shop.albaclick.de']
    start_urls = ('https://shop.albaclick.de/',)

    # PLZ für Stuttgart
    PLZ = '70193'
    CITY = 'Stuttgart'

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

        # Mapping für Abfallart-Umbenennungen
        self.waste_type_mapping = {
            'Pappe | Papier': 'Papier/Pappe',
            'Grünschnitt | Gartenabfälle': 'Gartenabfälle',
            'E-Geräte (Kleingeräte)': 'Elektrokleingeräte',
            'E-Geräte (Großgeräte)': 'Elektrogroßgeräte',
            'Baumisch (leicht)': 'Baumischabfall (leicht)',
            'Holz A1 - A3': 'Holz A1-A3',
        }

    def _dismiss_cookie_banner(self):
        """Schließt OneTrust Cookie-Banner."""
        if self.cookie_dismissed:
            return

        cookie_selectors = [
            "//button[text()='Alle akzeptieren']",
            "//button[contains(text(), 'Alle akzeptieren')]",
            "//button[@id='onetrust-accept-btn-handler']",
            "//button[contains(@class, 'onetrust')]",
            "//button[contains(text(), 'Accept')]",
            "//button[contains(text(), 'Akzeptieren')]",
        ]

        for selector in cookie_selectors:
            try:
                element = WebDriverWait(self.driver, 3).until(
                    EC.element_to_be_clickable((By.XPATH, selector))
                )
                self.driver.execute_script("arguments[0].click();", element)
                self.log("✓ Cookie-Banner geschlossen")
                self.cookie_dismissed = True
                sleep(1)
                return
            except:
                pass

    def _js_click(self, xpath):
        """JavaScript-Klick für robustere Interaktion."""
        try:
            element = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.XPATH, xpath))
            )
            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
            sleep(0.5)
            self.driver.execute_script("arguments[0].click();", element)
            return True
        except Exception as e:
            self.log(f"Klick fehlgeschlagen für {xpath}: {e}")
            return False

    def closed(self, reason):
        try:
            self.driver.quit()
        except:
            pass

    def parse(self, response):
        waste_types = [
            'pappe-papier',
            'sperrmuell',
            'baumischabfall',
            'bauschutt',
            'holz-A1-A3',
            'holz-A4',
            'gruenschnitt-gartenabfaelle',
            'kunststoff-verpackungen',
            'elektro-kleingeraete',
            'elektro-grossgeraete'
        ]

        self.log(f"\n{'='*80}")
        self.log(f"Starte Alba Click Scraping für {self.CITY} (PLZ: {self.PLZ})")
        self.log(f"{'='*80}\n")

        total_products = 0

        for waste_type in waste_types:
            url = f'https://shop.albaclick.de/{waste_type}/{self.PLZ}-{self.CITY}/privat/produkt?postCode={self.PLZ}'
            self.driver.get(url)
            sleep(4)

            self.log(f'\n--- Verarbeite: {waste_type} ---')
            self.log(f'URL: {self.driver.current_url}')

            # Prüfe ob Seite verfügbar ist
            if 'nicht verfügbar' in self.driver.page_source.lower() or 'nicht lieferbar' in self.driver.page_source.lower():
                self.log(f'  Nicht verfügbar für {self.CITY}')
                continue

            # Cookie-Banner schließen (OneTrust)
            self._dismiss_cookie_banner()

            max_rental_period = '7 Tage'

            # JavaScript-Klick für "Welche Größe?" Button
            self._js_click('//button[contains(@aria-label, "Welche Größe?")]')
            sleep(3)

            sel = Selector(text=self.driver.page_source)

            options = sel.xpath('//div[@class="variant-configuration-variants"]/button')

            for option in options:
                title = option.xpath('.//div[@class="variant-configuration-variants-item__variant"]/span/text()').get()

                # Überspringe "Flexibler" und "240 Liter" (Umleerbehälter)
                if not title or 'Flexibler' in title or '240 Liter' in title:
                    continue

                type_raw = sel.xpath('//div[@itemprop="itemListElement"]')[1].xpath('.//span/text()').get()

                # Wende Mapping an für Umbenennungen
                waste_type_mapped = self.waste_type_mapping.get(type_raw, type_raw)

                regex_match = re.search(r'\b\d+(?:[.,]\d+)?\s?(?:m³|m3|liter|litre)\b', title, re.IGNORECASE)
                size = (regex_match.group() if regex_match else None)

                price = option.xpath('.//div[@class="variant-configuration-variants-item__price"]/span/text()').get()
                if price:
                    price = price.replace('€', '').strip()

                item = {
                    'source': 'Alba Click',
                    'title': title,
                    'type': waste_type_mapped,
                    'city': self.CITY,
                    'size': size,
                    'price': price,
                    'lid_price': '17,85',
                    'arrival_price': 'inklusive',
                    'departure_price': 'inklusive',
                    'max_rental_period': max_rental_period,
                    'fee_after_max': None,
                    'cancellation_fee': '151,00',
                    'URL': self.driver.current_url
                }

                total_products += 1
                self.log(f"  ✓ {size}: {price} EUR")
                yield item

        self.log(f"\n{'='*80}")
        self.log(f"Gesamt gescrapt: {total_products} Produkte")
        self.log(f"{'='*80}\n")
