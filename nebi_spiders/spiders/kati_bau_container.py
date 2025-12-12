"""
Kati Bau Spider
Extrahiert Preise für Container-Entsorgung in Berlin
Preisliste basierend auf PDF vom 01.01.2020
"""

import scrapy


class KatiBauContainerSpider(scrapy.Spider):
    name = "kati-bau-container"
    allowed_domains = ["kati-bau.de"]
    start_urls = ["https://www.kati-bau.de/"]

    # Container sizes available (in m³)
    CONTAINER_SIZES = [3, 7]

    # VAT rate
    VAT_RATE = 1.19  # 19% MwSt.

    # Empty trip fee (Leerfahrt)
    EMPTY_TRIP_FEE_NET = 80.00
    EMPTY_TRIP_FEE_WITH_VAT = round(EMPTY_TRIP_FEE_NET * VAT_RATE, 2)  # 95.20€

    # Rental fees for 9+ days (per day)
    RENTAL_FEE_ABSETZCONTAINER = 3.00  # already gross (brutto)
    RENTAL_FEE_ABROLLCONTAINER = 7.00  # already gross (brutto)

    custom_settings = {
        'USER_AGENT': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
        'ROBOTSTXT_OBEY': True,
        'CONCURRENT_REQUESTS': 1,
        'DOWNLOAD_DELAY': 2,
    }

    def parse(self, response):
        """Parse price list and generate products"""

        self.logger.info("Generating Kati Bau products from price list")

        # Waste types with their net prices (from PDF Preisliste 01.01.2020)
        # Format: {
        #   'name': 'Display name',
        #   'prices': {3: price_net, 7: price_net},
        #   'container_type': 'Absetzcontainer' or 'Abrollcontainer'
        # }

        waste_types = [
            {
                'name': 'Bauschutt',
                'prices': {3: 315.00, 7: 490.00},
                'container_type': 'Absetzcontainer'
            },
            {
                'name': 'Bauschutt (nicht recyclingfähig)',
                'prices': {3: 340.00, 7: 530.00},
                'container_type': 'Absetzcontainer'
            },
            {
                'name': 'Baumisch (ohne Wertstoffe)',
                'prices': {3: 470.00, 7: 730.00},
                'container_type': 'Absetzcontainer'
            },
            {
                'name': 'Holz A1-A3',
                'prices': {3: 290.00, 7: 445.00},
                'container_type': 'Absetzcontainer'
            },
            {
                'name': 'Holz A4',
                'prices': {3: 370.00, 7: 565.00},
                'container_type': 'Absetzcontainer'
            },
            {
                'name': 'Laub/Gras',
                'prices': {3: 290.00, 7: 445.00},
                'container_type': 'Absetzcontainer'
            },
            {
                'name': 'Grünabfall Äste',
                'prices': {3: 290.00, 7: 445.00},
                'container_type': 'Absetzcontainer'
            },
            {
                'name': 'Sperrmüll',
                'prices': {3: 290.00, 7: 445.00},
                'container_type': 'Absetzcontainer'
            },
            {
                'name': 'Dämmwolle',
                'prices': {3: 370.00, 7: 565.00},
                'container_type': 'Absetzcontainer'
            },
            {
                'name': 'Asbest',
                'prices': {3: 605.00, 7: 935.00},
                'container_type': 'Absetzcontainer'
            },
        ]

        # Generate products for each waste type
        for waste_info in waste_types:
            waste_name = waste_info['name']
            container_type = waste_info['container_type']

            # Determine rental fee per day for 9+ days
            if container_type == 'Absetzcontainer':
                rental_fee_per_day = self.RENTAL_FEE_ABSETZCONTAINER
            else:
                rental_fee_per_day = self.RENTAL_FEE_ABROLLCONTAINER

            for size, price_net in waste_info['prices'].items():
                price_with_vat = round(price_net * self.VAT_RATE, 2)

                yield {
                    "source": "Kati Bau",
                    "title": f"{size} m³ {waste_name}",
                    "type": waste_name,
                    "city": "Berlin",
                    "size": str(size),
                    "price": f"{price_with_vat:.2f}".replace('.', ','),
                    "lid_price": "",
                    "arrival_price": "Anbieter anfragen",
                    "departure_price": "Anbieter anfragen",
                    "max_rental_period": "9",
                    "fee_after_max": str(rental_fee_per_day),
                    "cancellation_fee": f"{self.EMPTY_TRIP_FEE_WITH_VAT:.2f}".replace('.', ','),
                    "URL": "https://www.kati-bau.de/wp-content/uploads/2020/12/Preisliste-2019-12.pdf",
                }
