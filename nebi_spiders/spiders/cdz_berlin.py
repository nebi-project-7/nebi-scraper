import re
import requests
from scrapy import Spider
from scrapy.selector import Selector
from scrapy.shell import inspect_response
from scrapy.http import Request, FormRequest
from scrapy.utils.response import open_in_browser


def get_cancellation_fee(html_text):
    sel = Selector(text=html_text)
    data_point = sel.xpath(
        '//p[contains(text(), "Bei einer vergeblichen Anfahrt/Nichtabnahme")]/following-sibling::ul[1]//text()').getall()

    data_point = [dp.strip() for dp in data_point]
    data_point = [dp for dp in data_point if dp != '']
    data_point = '\n'.join(data_point).strip()

    return data_point

class CdzBerlinSpider(Spider):
    name = 'cdz-berlin'
    allowed_domains = ['cdz-berlin.de']
    start_urls = ['https://cdz-berlin.de/shop.php']

    def __init__(self):
        page = requests.get('https://cdz-berlin.de/allgemeine_geschaeftsbedingungen')

        self.max_rental_period = re.findall(r'(?<=bis zu )(\d+)(?= Tagen)', page.text)[0]
        self.fee_after_max = re.findall(r'(?<=von )([\d,]+)(?= €)', page.text)[0]
        self.cancellation_fee = get_cancellation_fee(page.text)

    def parse(self, response):
        # open_in_browser(response)
        # inspect_response(response, self)

        categories = response.xpath('//div[contains(@class, "product-category product")]/a/@href').getall()
        for category_url in categories:
            yield Request(category_url,
                          callback=self.parse_category)

    def parse_category(self, response):
        # open_in_browser(response)
        # inspect_response(response, self)

        containers = response.xpath('//a[@class="title-item"]/@href').getall()
        if containers:
            for container_url in containers:
                yield Request(container_url,
                              callback=self.parse_container)

        else:
            categories = response.xpath('//div[contains(@class, "product-category product")]/a/@href').getall()
            for category_url in categories:
                yield Request(category_url,
                              callback=self.parse_category)

    def parse_container(self, response):
        # open_in_browser(response)
        # inspect_response(response, self)

        source = 'cdz-berlin.de'

        title = response.xpath('//h1[@class="product_title entry-title"]/text()').get()

        type = response.xpath('//span[@class="posted_in"]/a/text()').get()
        # Umbenennung: Holz A IV → Holz A4
        if type == 'Holz A IV':
            type = 'Holz A4'

        city = 'Berlin'

        size = re.findall(r'(\d+(?:[.,]\d+)?)\s*m³', response.text)[0]

        try:
            price = re.findall('"range_cost":"(.*?)",', response.text)[0]
        except IndexError:
            price = ''

        if price:
            lid_price = response.xpath('//input[@data-name="Containerdeckel"]/@data-value').get()

            if 'cdz-berlin.de/wp-content/uploads/2021/01/Logo2-300x89.png' in response.text:
                arrival_price = 'inklusive'
                departure_price = 'inklusive'
            else:
                arrival_price = ''
                departure_price = ''

            item = {'source': source,
                    'title': title,
                    'type': type,
                    'city': city,
                    'size': size,
                    'price': price,
                    'lid_price': lid_price,
                    'arrival_price': arrival_price,
                    'departure_price': departure_price,
                    'max_rental_period': self.max_rental_period,
                    'fee_after_max': self.fee_after_max,
                    'cancellation_fee': self.cancellation_fee,
                    'URL': response.url}

            yield item
