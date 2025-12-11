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


class ContainerfritzeSpider(Spider):
    name = 'containerfritze'
    start_urls = ['https://containerfritze.de/']

    def __init__(self):
        self.driver = webdriver.Chrome()
        self.driver.maximize_window()

        # page = requests.get('https://containerfritze.de/agb/')

        # try:
        #     self.cancellation_fee = re.findall(r'(?<=Kunden mit )(\d+)(?= Euro)', page.text)[0]
        # except:
        #     self.cancellation_fee = ''

        self.cancellation_fee = '180'

        logging.getLogger('selenium').setLevel(logging.WARNING)
        logging.getLogger('urllib3').setLevel(logging.WARNING)

    def parse(self, response):
        # open_in_browser(response)
        # inspect_response(response, self)

        start_urls = ['https://containerfritze.de/dienste/entsorgung-berlin/',
                      'https://containerfritze.de/dienste/entsorgung-berlin/page/2/',
                      'https://containerfritze.de/dienste/entsorgung-berlin/page/3/']

        for start_url in start_urls:
            self.driver.get(start_url)
            sleep(3)

            containers = Selector(text=self.driver.page_source).xpath('//h2/a/@href').getall()
            for container in containers:

                self.driver.get(container)
                sleep(3)

                order_now_button_url = Selector(text=self.driver.page_source).xpath(
                    '//a[@class="elementor-button elementor-button-link elementor-size-lg"]/@href').get()

                if order_now_button_url:
                    self.driver.get(order_now_button_url)
                    sleep(4)

                    try:
                        self.driver.find_element('xpath', '//span[text()="Brutto"]').click()
                        sleep(3)
                    except:
                        pass
                    try:
                        self.driver.find_element('xpath', '//li/a[text()="Privat"]').click()
                        sleep(2)
                    except:
                        pass
                    try:
                        self.driver.find_element('xpath', '//span[text()="Brutto"]').click()
                        sleep(3)
                    except:
                        pass

                    containers = self.driver.find_elements('xpath', '//ul[@data-attribute="attribute_pa_groesse"]/li/a')
                    for container_num, container in enumerate(containers):
                        self.driver.find_elements('xpath', '//ul[@data-attribute="attribute_pa_groesse"]/li/a')[container_num].click()
                        sleep(3)

                        sel = Selector(text=self.driver.page_source)

                        source = 'containerfritze'

                        title = sel.xpath('//strong[text()="Größe"]/following-sibling::span/text()').getall()
                        if title:
                            title = ' '.join(title).replace(':', '').strip()
                        else:
                            title = ''

                        type = sel.xpath('//nav[@aria-label="Breadcrumb"]/a[3]/text()').get()

                        city = 'Berlin'

                        regex_match = re.search(r'\b\d+(?:[.,]\d+)?\s?(?:m³|m3|liter|litre)\b', title, re.IGNORECASE)
                        size = (regex_match.group() if regex_match else None)

                        # price = (sel.xpath('//input[@id="pewc-product-price"]/@value').get() or '').replace(',', '.')
                        price = sel.xpath('//div[@class="inklMWST"]//span[@class="woocommerce-Price-amount amount"]/bdi/text()').get()
                        if price:
                            price = price.replace(',00', '').strip()
                            price = price.replace('.', ',')

                            lid_price = sel.xpath('//option[@value="Mit Abdeckung  +"]/@data-option-cost').get()

                            match = re.search(r'\d+', sel.xpath('//strong[contains(text(), "max.")]/text()').get())
                            if match:
                                max_rental_period = match.group(0)
                            else:
                                max_rental_period = ''

                            arrival_price = 'free'
                            departure_price = 'free'

                            try:
                                fee_after_max = re.findall(r'(?<=werden nachträglich mit )([\d,]+)(?= €)', sel.extract())[0]
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
