"""
Kroll Entsorgung Spider
Extrahiert Preise für Container-Entsorgung in Berlin
"""

import scrapy
import re


class KrollContainerSpider(scrapy.Spider):
    name = "kroll-container"
    allowed_domains = ["kroll-entsorgung.com"]
    start_urls = ["https://kroll-entsorgung.com/preisliste/"]

    # Container sizes available (in m³)
    CONTAINER_SIZES = [3, 5.5, 7, 10]

    # VAT rate
    VAT_RATE = 1.19  # 19% MwSt.

    # Delivery charge (Anfahrtskosten Berlin + Ludwigsfelde)
    ARRIVAL_PRICE_NET = 52.00
    ARRIVAL_PRICE_WITH_VAT = round(ARRIVAL_PRICE_NET * VAT_RATE, 2)  # 61.88€

    custom_settings = {
        'USER_AGENT': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
        'ROBOTSTXT_OBEY': True,
        'CONCURRENT_REQUESTS': 1,
        'DOWNLOAD_DELAY': 2,
    }

    def parse(self, response):
        """Parse price list page and extract all prices"""

        self.logger.info("Parsing Kroll Entsorgung price list")

        # Define waste types with their pricing structure
        # Format: {
        #   'name': 'Display name',
        #   'type': 'flat' or 'per_m3',
        #   'prices': {3: price, 5.5: price, 7: price, 10: price} or price_per_m3
        # }

        waste_types = [
            {
                'name': 'Baumischabfall leicht',
                'type': 'flat',
                'prices': {3: 290.00, 5.5: 515.00}
            },
            {
                'name': 'Baumischabfall schwer',
                'type': 'flat',
                'prices': {3: 315.00, 5.5: 577.50}
            },
            {
                'name': 'Beton',
                'type': 'flat',
                'prices': {3: 150.00, 5.5: 250.00, 7: 315.00}
            },
            {
                'name': 'Bauschutt',
                'type': 'flat',
                'prices': {3: 206.00, 5.5: 375.00, 7: 478.00}
            },
            {
                'name': 'Gemischter Bauschutt',
                'type': 'flat',
                'prices': {3: 240.00, 5.5: 431.00, 7: 546.00}
            },
            {
                'name': 'Erdaushub',
                'type': 'flat',
                'prices': {3: 206.00, 5.5: 375.00, 7: 478.00}
            },
            {
                'name': 'Bauholz AIII',
                'type': 'flat',
                'prices': {3: 180.00, 5.5: 315.00, 7: 399.00}
            },
            {
                'name': 'Gartenabfall',
                'type': 'flat',
                'prices': {3: 101.00, 5.5: 185.00, 7: 220.00}
            },
            {
                'name': 'Sperrmüll',
                'type': 'flat',
                'prices': {3: 291.00}
            },
            {
                'name': 'Styropor',
                'type': 'per_m3',
                'price_per_m3': 125.00,
                'available_sizes': [3, 5.5, 7]  # Assuming not available for 10m³
            },
            {
                'name': 'Dämmwolle',
                'type': 'per_m3',
                'price_per_m3': 125.00,
                'available_sizes': [3, 5.5, 7]  # Assuming not available for 10m³
            },
        ]

        # Generate products for each waste type
        for waste_info in waste_types:
            waste_name = waste_info['name']

            if waste_info['type'] == 'flat':
                # Flat rate pricing - use specific prices for each size
                for size, price_net in waste_info['prices'].items():
                    price_with_vat = round(price_net * self.VAT_RATE, 2)

                    # Lid only available for 3m³ containers
                    has_lid = "inklusive" if size == 3 else "nein"
                    lid_price = "im Preis enthalten" if size == 3 else "nicht verfügbar"

                    yield {
                        "source": "Kroll Entsorgung",
                        "type": waste_name,
                        "city": "Berlin",
                        "size": str(size),
                        "price": str(price_with_vat),
                        "price_without_vat": str(price_net),
                        "max_rental_period": "nicht angegeben",
                        "lid_available": has_lid,
                        "lid_price": lid_price,
                        "arrival_price": str(self.ARRIVAL_PRICE_WITH_VAT),
                        "departure_price": "inklusive",
                        "URL": response.url,
                    }

            elif waste_info['type'] == 'per_m3':
                # Price per m³ - calculate for each available size
                price_per_m3 = waste_info['price_per_m3']
                available_sizes = waste_info.get('available_sizes', self.CONTAINER_SIZES)

                for size in available_sizes:
                    price_net = price_per_m3 * size
                    price_with_vat = round(price_net * self.VAT_RATE, 2)

                    # Lid only available for 3m³ containers
                    has_lid = "inklusive" if size == 3 else "nein"
                    lid_price = "im Preis enthalten" if size == 3 else "nicht verfügbar"

                    yield {
                        "source": "Kroll Entsorgung",
                        "type": waste_name,
                        "city": "Berlin",
                        "size": str(size),
                        "price": str(price_with_vat),
                        "price_without_vat": str(price_net),
                        "max_rental_period": "nicht angegeben",
                        "lid_available": has_lid,
                        "lid_price": lid_price,
                        "arrival_price": str(self.ARRIVAL_PRICE_WITH_VAT),
                        "departure_price": "inklusive",
                        "URL": response.url,
                    }
