import re
import logging
import requests
from time import sleep
from scrapy import Spider
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from scrapy.selector import Selector
from scrapy.shell import inspect_response
from scrapy.http import Request, FormRequest
from scrapy.utils.response import open_in_browser


class AlbaclickSpider(Spider):
    name = 'albaclick'
    allowed_domains = ['shop.albaclick.de']
    start_urls = ('https://shop.albaclick.de/',)

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
            'Pappe | Papier': 'Pappe, Papier und Kartonage',
            'Grünschnitt | Gartenabfälle': 'Gartenabfälle',
            'E-Geräte (Kleingeräte)': 'Elektrokleingeräte',
            'E-Geräte (Großgeräte)': 'Elektrogroßgeräte',
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
        # open_in_browser(response)
        # inspect_response(response, self)

        waste_types = ['pappe-papier',
                       'sperrmuell',
                       'baumischabfall',
                       'bauschutt',
                       'holz-A1-A3',
                       'holz-A4',
                       'gruenschnitt-gartenabfaelle',
                       'kunststoff-verpackungen',
                       'elektro-kleingeraete',
                       'elektro-grossgeraete']

        for waste_type in waste_types:

            post_codes = ['10115']
            for post_code in post_codes:

                self.driver.get(f'https://shop.albaclick.de/{waste_type}/{post_code}-Berlin/privat/produkt?postCode={post_code}')
                sleep(4)

                self.log(f'Processing: {self.driver.current_url}')

                # Cookie-Banner schließen (OneTrust)
                self._dismiss_cookie_banner()

                max_rental_period = '7'

                # JavaScript-Klick für "Welche Größe?" Button
                self._js_click('//button[contains(@aria-label, "Welche Größe?")]')
                sleep(3)

                sel = Selector(text=self.driver.page_source)

                options = sel.xpath('//div[@class="variant-configuration-variants"]/button')

                for option in options:

                    source = 'albaclick'

                    title = option.xpath('.//div[@class="variant-configuration-variants-item__variant"]/span/text()').get()

                    # Überspringe "Flexibler" und "240 Liter" (Umleerbehälter)
                    if 'Flexibler' in title or '240 Liter' in title:
                        continue

                    type = sel.xpath('//div[@itemprop="itemListElement"]')[1].xpath('.//span/text()').get()

                    # Wende Mapping an für Umbenennungen
                    if type in self.waste_type_mapping:
                        type = self.waste_type_mapping[type]

                    city = 'Berlin'

                    regex_match = re.search(r'\b\d+(?:[.,]\d+)?\s?(?:m³|m3|liter|litre)\b', title, re.IGNORECASE)
                    size = (regex_match.group() if regex_match else None)

                    price = option.xpath('.//div[@class="variant-configuration-variants-item__price"]/span/text()').get()
                    price = price.replace('€', '').strip()

                    lid_price = '17,85'

                    arrival_price = 'inklusive'
                    departure_price = 'inklusive'
                    fee_after_max = ''
                    cancellation_fee = '151,00'

                    item = {'source': source,
                            'title': title,
                            'type': type,
                            'city': city,
                            'size': size,
                            'price': price,
                            'lid_price': lid_price,
                            'arrival_price': arrival_price,
                            'departure_price': departure_price,
                            'max_rental_period': max_rental_period,
                            'fee_after_max': fee_after_max,
                            'cancellation_fee': cancellation_fee,
                            'URL': self.driver.current_url}

                    yield item
