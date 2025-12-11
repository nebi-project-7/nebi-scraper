"""
ABC-Containerdienst Spider
Extrahiert Preise für Container-Entsorgung in Berlin
"""

import scrapy
import re


class ABCContainerSpider(scrapy.Spider):
    name = "abc-container"
    allowed_domains = ["abc-containerdienst.de"]
    start_urls = ["https://abc-containerdienst.de/abfall-entsorgen-berlin/"]

    # Container sizes available
    CONTAINER_SIZES = [3, 5, 7, 8, 10]

    # VAT rate
    VAT_RATE = 1.19  # 19% MwSt.

    custom_settings = {
        'USER_AGENT': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
        'ROBOTSTXT_OBEY': True,
        'CONCURRENT_REQUESTS': 1,
        'DOWNLOAD_DELAY': 2,
    }

    def parse(self, response):
        """Parse overview page and extract waste type links"""

        # Hardcoded list of all 10 waste type pages (to ensure we get all of them)
        detail_pages = [
            "https://abc-containerdienst.de/baumisch-entsorgen/",
            "https://abc-containerdienst.de/bauschutt-entsorgen-berlin/",
            "https://abc-containerdienst.de/beton-entsorgen/",
            "https://abc-containerdienst.de/daemmmaterial-entsorgen/",
            "https://abc-containerdienst.de/erdaushub-entsorgen/",
            "https://abc-containerdienst.de/gartenabfall-entsorgen-berlin/",
            "https://abc-containerdienst.de/gipsabfall-entsorgen/",
            "https://abc-containerdienst.de/holz-entsorgen/",
            "https://abc-containerdienst.de/sperrmuell-entsorgen/",
            "https://abc-containerdienst.de/teerhaltige-abfaelle/",
        ]

        self.logger.info(f"Visiting {len(detail_pages)} waste type pages")

        # Visit each detail page
        for url in detail_pages:
            yield response.follow(url, callback=self.parse_waste_type)

    def parse_waste_type(self, response):
        """Parse waste type detail page and extract prices"""

        # Extract waste type name from URL
        # e.g., https://abc-containerdienst.de/baumisch-entsorgen/ -> Baumisch
        url_parts = response.url.rstrip('/').split('/')
        waste_slug = url_parts[-1]
        waste_type = self.clean_waste_name(waste_slug)

        self.logger.info(f"Processing: {waste_type}")

        # Extract price information from the page
        # Look for patterns like "315,- €" or "85,- €"
        text_content = ' '.join(response.xpath('//text()').getall())

        # Extract prices from table cells
        table_prices = response.xpath('//td[contains(text(), "€")]/text()').getall()

        flat_rate_3m3 = None
        price_per_m3 = None

        if table_prices:
            self.logger.info(f"  Found table prices: {table_prices}")
            # Extract numbers from price strings like "315,00 €"
            extracted_prices = []
            for price_text in table_prices:
                # Match prices like "315,00 €" or "315,- €" or "85,- €"
                price_match = re.search(r'(\d+)[,\.](\d+)?\s*€', price_text)
                if price_match:
                    integer_part = price_match.group(1)
                    decimal_part = price_match.group(2) if price_match.group(2) else "00"
                    price_value = float(f"{integer_part}.{decimal_part}")
                    extracted_prices.append(price_value)

            # First price is typically 3m³ flat rate, second is price per m³
            if len(extracted_prices) >= 2:
                flat_rate_3m3 = extracted_prices[0]
                price_per_m3 = extracted_prices[1]
                self.logger.info(f"  Extracted: 3m³ flat rate = {flat_rate_3m3}€, per m³ = {price_per_m3}€")
            elif len(extracted_prices) == 1:
                # Only one price found, assume it's the per m³ price
                price_per_m3 = extracted_prices[0]
                self.logger.info(f"  Extracted: per m³ = {price_per_m3}€")

        # If still no prices found, log warning and skip
        if not flat_rate_3m3 and not price_per_m3:
            self.logger.warning(f"  No prices found for {waste_type}")
            return

        # Generate products for each container size
        for size in self.CONTAINER_SIZES:
            price_without_vat = self.calculate_price_without_vat(size, flat_rate_3m3, price_per_m3)

            if price_without_vat is None:
                continue

            # Calculate final price with VAT
            price_with_vat = round(price_without_vat * self.VAT_RATE, 2)

            yield {
                "source": "ABC-Containerdienst",
                "type": waste_type,
                "city": "Berlin",
                "size": str(size),
                "price": str(price_with_vat),
                "price_without_vat": str(price_without_vat),
                "max_rental_period": "10",
                "cancellation_fee": "Preis anfragen",
                "URL": response.url,
            }

    def calculate_price_without_vat(self, size, flat_rate_3m3, price_per_m3):
        """Calculate price without VAT based on container size"""

        if size == 3:
            # 3m³ uses flat rate
            if flat_rate_3m3:
                return flat_rate_3m3
            else:
                return None
        elif size >= 5 and size <= 10:
            # 5-10m³ uses price per m³
            if price_per_m3:
                return size * price_per_m3
            else:
                return None
        else:
            return None

    def clean_waste_name(self, slug):
        """Convert URL slug to readable waste type name"""

        # Remove '-entsorgen', '-berlin', etc.
        name = slug.replace('-entsorgen', '')
        name = name.replace('-berlin', '')
        name = name.replace('-', ' ')

        # Capitalize
        name = name.title()

        # Special mappings
        mappings = {
            'baumisch': 'Baumischabfall',
            'bauschutt': 'Bauschutt',
            'beton': 'Beton',
            'daemmmaterial': 'Dämmmaterial',
            'erdaushub': 'Erdaushub',
            'gartenabfall': 'Gartenabfall',
            'gipsabfall': 'Gipsabfall',
            'holz': 'Holz',
            'sperrmuell': 'Sperrmüll',
            'teerhaltige': 'Teerhaltige Abfälle',
        }

        for key, value in mappings.items():
            if key.lower() in name.lower():
                return value

        return name
