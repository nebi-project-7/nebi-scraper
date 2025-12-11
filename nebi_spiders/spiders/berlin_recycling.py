import re
import logging
import requests
from time import sleep
from scrapy import Spider
from selenium import webdriver
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

    def parse(self, response):
        # open_in_browser(response)
        # inspect_response(response, self)

        containers = response.xpath('//div[contains(@class, "grid w-full gap-4")]/a/@href').getall()
        for container in containers:

            source = 'shop.berlin-recycling.de'

            self.driver.get(response.urljoin(container))
            sleep(2.5)

            try:
                self.driver.find_element('xpath', '//button[@title="Akzeptieren Sie alle cookies"]').click()
                sleep(0.5)
            except:
                pass

            if Selector(text=self.driver.page_source).xpath('//span[text()="Infos zum Ablauf (Vorlaufzeit, Terminvereinbarung & Rechnung)"]'):
                pass
            else:
                try:
                    option_values = Selector(text=self.driver.page_source).xpath(
                        '//dd/select')[0].xpath('.//option[not(@disabled)]/@value').getall()
                except:
                    input('Waiting')

                for option_value in option_values:
                    self.driver.find_element('xpath', f'//option[@value="{option_value}"]').click()
                    sleep(3)

                    self.log(f'Processing: {self.driver.current_url}')
                    sel = Selector(text=self.driver.page_source)

                    title = sel.xpath('//h1/text()').get()

                    type = sel.xpath('//a[@class="transition-colors hover:text-foreground"]/text()').getall()[-1]

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
