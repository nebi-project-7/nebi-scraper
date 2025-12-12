import re
import logging
import requests
from time import sleep
from scrapy import Spider
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, ElementClickInterceptedException
from scrapy.selector import Selector
from scrapy.shell import inspect_response
from scrapy.http import Request, FormRequest
from scrapy.utils.response import open_in_browser


class ContainerfritzeSpider(Spider):
    name = 'containerfritze'
    start_urls = ['https://containerfritze.de/']

    def __init__(self):
        options = webdriver.ChromeOptions()
        options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.add_argument('--window-size=1920,1080')
        self.driver = webdriver.Chrome(options=options)

        # page = requests.get('https://containerfritze.de/agb/')

        # try:
        #     self.cancellation_fee = re.findall(r'(?<=Kunden mit )(\d+)(?= Euro)', page.text)[0]
        # except:
        #     self.cancellation_fee = ''

        self.cancellation_fee = '180'

        logging.getLogger('selenium').setLevel(logging.WARNING)
        logging.getLogger('urllib3').setLevel(logging.WARNING)

        # Mapping von URL-Slugs zu korrekten Abfallart-Namen
        self.waste_type_mapping = {
            'baumischabfall-leicht': 'Baumischabfall leicht',
            'baumischabfall-schwer': 'Baumischabfall schwer',
            'betonbruch-bewehrt-mit-stahl': 'Betonbruch bewehrt mit Stahl',
            'betonbruch-unbewehrt-ohne-stahl': 'Betonbruch unbewehrt ohne Stahl',
            'daemmwolle': 'Dämmstoffe',
            'erdaushub-mit-grasnarbe': 'Erdaushub mit Grasnarbe',
            'erdaushub-mit-steinen': 'Erdaushub mit Steinen',
            'erdaushub-ohne-fremdanteil': 'Erdaushub ohne Fremdanteil',
            'flachglas': 'Flachglas',
            'gartenabfall-gemischt': 'Gartenabfälle',
            'gruenschnitt': 'Grünschnitt',
            'gewerbeabfall-gemischt': 'Gewerbeabfall',
            'gipsabfaelle': 'Gips',
            'glasverpackungen': 'Glasverpackungen',
            'holz-a1-a3': 'Holz A1-A3',
            'holz-a1': 'Holz A1',
            'holz-a2-a3': 'Holz A2-A3',
            'holz-a4': 'Holz A4',
            'porenbeton': 'Porenbeton',
            'bauschutt': 'Bauschutt',
            'bauschutt-recyclingfaehig': 'Bauschutt recyclingfähig',
            'bauschutt-nicht-recyclingfaehig': 'Bauschutt nicht recyclingfähig',
            'styropor-mit-anhaftungen': 'Styropor mit Anhaftungen',
            'styropor-ohne-anhaftungen': 'Styropor ohne Anhaftungen',
            'verpackungsstyropor': 'Verpackungsstyropor',
            'sperrmuell': 'Sperrmüll',
            'sperrmuell-gemischt': 'Sperrmüll',
            'siedlungsabfall-gemischt': 'Siedlungsabfall',
            'papier-pappe': 'Papier/Pappe',
            'folie': 'Folie',
            'lehmboden': 'Lehmboden',
            'sand': 'Sand',
            'steine': 'Steine',
        }

    def _dismiss_cookie_banner(self):
        """Versucht Cookie-Banner zu schließen."""
        cookie_selectors = [
            "//button[contains(text(), 'Akzeptieren')]",
            "//button[contains(text(), 'Alle akzeptieren')]",
            "//button[contains(text(), 'Accept')]",
            "//a[contains(text(), 'Akzeptieren')]",
            "//button[contains(@class, 'cookie')]",
            "//div[contains(@class, 'cookie')]//button",
        ]
        for selector in cookie_selectors:
            try:
                elements = self.driver.find_elements(By.XPATH, selector)
                for elem in elements:
                    if elem.is_displayed():
                        self._js_click(elem)
                        self.log("✓ Cookie-Banner geschlossen")
                        sleep(1)
                        return True
            except:
                pass
        return False

    def _js_click(self, element):
        """Führt JavaScript-Klick aus um Overlay-Probleme zu vermeiden."""
        self.driver.execute_script("arguments[0].click();", element)

    def _extract_waste_type_from_url(self, url):
        """Extrahiert den Abfallart-Namen aus der URL."""
        # URL: https://shop.containerfritze.de/mieten/baumischabfall-leicht-container/
        # -> baumischabfall-leicht
        try:
            # Extrahiere den Slug aus der URL (zwischen /mieten/ und -container)
            match = re.search(r'/mieten/([^/]+)-container', url)
            if match:
                slug = match.group(1)
                # Schaue im Mapping nach
                if slug in self.waste_type_mapping:
                    return self.waste_type_mapping[slug]
                # Fallback: Slug formatieren
                return slug.replace('-', ' ').title()
        except:
            pass
        return None

    def _safe_click(self, xpath):
        """Sicherer Klick mit JavaScript-Fallback."""
        try:
            element = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.XPATH, xpath))
            )
            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
            sleep(0.5)
            self._js_click(element)
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

        start_urls = ['https://containerfritze.de/dienste/entsorgung-berlin/',
                      'https://containerfritze.de/dienste/entsorgung-berlin/page/2/',
                      'https://containerfritze.de/dienste/entsorgung-berlin/page/3/']

        for start_url in start_urls:
            self.driver.get(start_url)
            sleep(5)

            # Cookie-Banner beim ersten Laden schließen
            self._dismiss_cookie_banner()

            containers = Selector(text=self.driver.page_source).xpath('//h2/a/@href').getall()
            for container in containers:

                self.driver.get(container)
                sleep(5)

                # Cookie-Banner erneut prüfen
                self._dismiss_cookie_banner()

                order_now_button_url = Selector(text=self.driver.page_source).xpath(
                    '//a[@class="elementor-button elementor-button-link elementor-size-lg"]/@href').get()

                if order_now_button_url:
                    self.driver.get(order_now_button_url)
                    sleep(6)

                    # Cookie-Banner auf Produktseite schließen
                    self._dismiss_cookie_banner()

                    # JavaScript-Klicks statt normaler Klicks
                    self._safe_click('//span[text()="Brutto"]')
                    sleep(3)

                    self._safe_click('//li/a[text()="Privat"]')
                    sleep(3)

                    self._safe_click('//span[text()="Brutto"]')
                    sleep(3)

                    containers = self.driver.find_elements(By.XPATH, '//ul[@data-attribute="attribute_pa_groesse"]/li/a')
                    for container_num, container in enumerate(containers):
                        # JavaScript-Klick für Größen-Auswahl
                        size_elements = self.driver.find_elements(By.XPATH, '//ul[@data-attribute="attribute_pa_groesse"]/li/a')
                        if container_num < len(size_elements):
                            self._js_click(size_elements[container_num])
                        sleep(4)

                        sel = Selector(text=self.driver.page_source)

                        source = 'containerfritze'

                        title = sel.xpath('//strong[text()="Größe"]/following-sibling::span/text()').getall()
                        if title:
                            title = ' '.join(title).replace(':', '').strip()
                        else:
                            title = ''

                        # Extrahiere Abfallart aus URL statt Breadcrumb für genauere Bezeichnung
                        type = self._extract_waste_type_from_url(self.driver.current_url)
                        if not type:
                            # Fallback auf Breadcrumb
                            type = sel.xpath('//nav[@aria-label="Breadcrumb"]/a[3]/text()').get()

                        city = 'Berlin'

                        regex_match = re.search(r'\b\d+(?:[.,]\d+)?\s?(?:m³|m3|liter|litre)\b', title, re.IGNORECASE)
                        size = (regex_match.group() if regex_match else None)

                        # price = (sel.xpath('//input[@id="pewc-product-price"]/@value').get() or '').replace(',', '.')
                        price = sel.xpath('//div[@class="inklMWST"]//span[@class="woocommerce-Price-amount amount"]/bdi/text()').get()
                        if price:
                            price = price.strip()
                            # Im deutschen Format: Punkt = Tausendertrennzeichen, Komma = Dezimalzeichen
                            # Entferne IMMER alle Punkte (Tausendertrennzeichen)
                            # z.B. "1.071,00" -> "1071,00", "1.071" -> "1071"
                            price = price.replace('.', '')
                            # Entferne ",00" am Ende (ganze Zahlen)
                            price = price.replace(',00', '')

                            lid_price = sel.xpath('//option[@value="Mit Abdeckung  +"]/@data-option-cost').get()
                            if lid_price:
                                lid_price = lid_price.replace('.', ',')

                            match = re.search(r'\d+', sel.xpath('//strong[contains(text(), "max.")]/text()').get())
                            if match:
                                max_rental_period = match.group(0)
                            else:
                                max_rental_period = ''

                            arrival_price = 'inklusive'
                            departure_price = 'inklusive'

                            try:
                                fee_after_max = re.findall(r'(?<=werden nachträglich mit )([\d,]+)(?= €)', sel.extract())[0]
                                fee_after_max = fee_after_max + '€'
                            except:
                                fee_after_max = ''

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
                                    'cancellation_fee': self.cancellation_fee,
                                    'URL': self.driver.current_url}

                            yield item
