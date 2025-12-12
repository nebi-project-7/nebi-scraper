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
                sleep(3)

                self.log(f'Processing: {self.driver.current_url}')

                try:
                    self.driver.find_element('xpath', '//button[text()="Alle akzeptieren"]').click()
                    sleep(2)
                except:
                    pass

                # try:
                #     max_rental_period_sel = self.driver.find_elements('xpath', '//strong[contains(text(), "Tage Stellzeit")]')[-1].text
                #     max_rental_period = max_rental_period_sel.split()[0]
                # except:
                #     max_rental_period = ''
                max_rental_period = '7'

                self.driver.find_element('xpath', '//button[contains(@aria-label, "Welche Größe?")]').click()
                sleep(2)

                sel = Selector(text=self.driver.page_source)

                options = sel.xpath('//div[@class="variant-configuration-variants"]/button')

                for option in options:

                    source = 'albaclick'

                    title = option.xpath('.//div[@class="variant-configuration-variants-item__variant"]/span/text()').get()

                    if 'Flexibler' in title:
                        pass
                    else:
                        type = sel.xpath('//div[@itemprop="itemListElement"]')[1].xpath('.//span/text()').get()

                        city = 'Berlin'

                        regex_match = re.search(r'\b\d+(?:[.,]\d+)?\s?(?:m³|m3|liter|litre)\b', title, re.IGNORECASE)
                        size = (regex_match.group() if regex_match else None)

                        price = option.xpath('.//div[@class="variant-configuration-variants-item__price"]/span/text()').get()
                        price = price.replace('€', '').strip()

                        lid_price = '17,85'

                        arrival_price = 'free'
                        departure_price = 'free'
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
