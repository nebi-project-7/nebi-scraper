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


class BerlinRecyclingSpider(Spider):
    name = 'berlin-recycling'
    allowed_domains = ['shop.berlin-recycling.de']
    start_urls = ['https://shop.berlin-recycling.de/collections/container']

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

    def _dismiss_cookie_banner(self):
        """Schließt OneTrust Cookie-Banner."""
        if self.cookie_dismissed:
            return

        cookie_selectors = [
            "//button[@title='Akzeptieren Sie alle cookies']",
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

        containers = response.xpath('//div[contains(@class, "grid w-full gap-4")]/a/@href').getall()
        for container in containers:

            source = 'shop.berlin-recycling.de'

            self.driver.get(response.urljoin(container))
            sleep(3)

            # Cookie-Banner schließen (OneTrust)
            self._dismiss_cookie_banner()

            # Überspringe Produkte mit "Brandenburg" im Titel
            page_title = Selector(text=self.driver.page_source).xpath('//h1/text()').get() or ''
            if 'Brandenburg' in page_title:
                self.log(f'Überspringe Brandenburg-Produkt: {page_title}')
                continue

            if Selector(text=self.driver.page_source).xpath('//span[text()="Infos zum Ablauf (Vorlaufzeit, Terminvereinbarung & Rechnung)"]'):
                pass
            else:
                try:
                    option_values = Selector(text=self.driver.page_source).xpath(
                        '//dd/select')[0].xpath('.//option[not(@disabled)]/@value').getall()
                except:
                    input('Waiting')

                for option_value in option_values:
                    # JavaScript-Klick für Option
                    self._js_click(f'//option[@value="{option_value}"]')
                    sleep(3)

                    self.log(f'Processing: {self.driver.current_url}')
                    sel = Selector(text=self.driver.page_source)

                    title = sel.xpath('//h1/text()').get()

                    # Entferne "Container" aus dem Typ-Namen
                    type_raw = sel.xpath('//a[@class="transition-colors hover:text-foreground"]/text()').getall()[-1]
                    type = type_raw.replace('Container', '').replace('container', '').strip()

                    city = 'Berlin'

                    try:
                        size = re.findall(r'(\d+(?:[.,]\d+)?)\s*m³', option_value)[0]
                    except:
                        size = ''

                    if size:
                        price = sel.xpath('//p[@class="text-2xl font-semibold leading-8"]/text()').get()
                        if price:
                            price = price.replace('\xa0€', '')

                            lid_price = ''

                            arrival_price = 'free'
                            departure_price = 'free'

                            matches = (
                                re.findall(r'(?<=bis )([\d,]+)(?= Tage)', response.text)
                                or re.findall(r'(?<=& )([\d,]+)(?= Tage mietfrei)', response.text))
                            max_rental_period = matches[0] if matches else None

                            matches = (
                                re.findall(r'(\d+,\d+ € Nettopreis zzgl\. \d+% MwSt\. \([^)]*\))', response.text)
                                or re.findall(r'\d+,\d+\s€\snetto\szzgl\.\s\d+% MwSt\.\s\(\d+,\d+\s€\sbrutto\sinkl\.\s\d+% MwSt\.\)', response.text))
                            fee_after_max = matches[0] if matches else None

                            cancellation_fee = ''

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
