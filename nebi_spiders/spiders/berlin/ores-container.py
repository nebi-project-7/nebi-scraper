"""
ORES Containerlogistik Spider
Extrahiert Preise für Container-Entsorgung in Berlin

Shop: https://containerentsorgung-berlin.de/
Reines Scrapy — kein Selenium. Produktlisten und Detailseiten liefern
Links, Größen und Preise bereits im statischen HTML.
"""

import re

from scrapy import Spider, Request


class OresContainerProductsSpider(Spider):
    name = "ores-container-products"
    allowed_domains = ["containerentsorgung-berlin.de"]

    # Waste type URLs
    waste_type_urls = [
        ("https://containerentsorgung-berlin.de/Bauschutt-mineral.-oh.-Gipsanteile/", "Bauschutt mineral. oh. Gipsanteile"),
        ("https://containerentsorgung-berlin.de/Holz-Entsorgung/Holz-unbehandelt/", "Holz A1-A3"),
        ("https://containerentsorgung-berlin.de/Holz-Entsorgung/Holz-behandelt/", "Holz A4"),
        ("https://containerentsorgung-berlin.de/Gewerbeabfaelle/", "Gewerbeabfälle"),
        ("https://containerentsorgung-berlin.de/Sperrmuell/", "Sperrmüll"),
        ("https://containerentsorgung-berlin.de/Boden/", "Boden"),
        ("https://containerentsorgung-berlin.de/Bau-und-Abbruchabfaelle/", "Baumischabfall"),
        ("https://containerentsorgung-berlin.de/Gruenabfall-Laub-Grasschnitt/", "Gartenabfälle Laub Grasschnitt"),
        ("https://containerentsorgung-berlin.de/Strauchwerk/Strauchwerk-mit-Stammholz/", "Strauchwerk mit Stammholz"),
        ("https://containerentsorgung-berlin.de/Strauchwerk/Strauchwerk-ohne-Stammholz/", "Strauchwerk ohne Stammholz"),
    ]

    AGB_URL = "https://containerentsorgung-berlin.de/Informationen/Unsere-AGB/"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Rental period will be extracted from AGB
        self.max_rental_period = None
        self.total_products = 0

    def start_requests(self):
        """Zuerst die AGB lesen (Mietdauer), danach die Abfallarten."""
        self.logger.info("=" * 80)
        self.logger.info("Starte ORES Containerlogistik Scraping")
        self.logger.info("=" * 80)

        yield Request(
            url=self.AGB_URL,
            callback=self.parse_agb,
            errback=self.agb_failed,
            dont_filter=True,
        )

    def parse_agb(self, response):
        """Extrahiert die maximale Mietdauer aus der AGB-Seite."""
        visible_text = self.page_text(response)

        # Pattern: "max. 6 Kalendertagen" o.ä. in § 2
        rental_match = re.search(r'max\.\s*(\d+)\s*Kalendertag', visible_text, re.IGNORECASE)
        if rental_match:
            self.max_rental_period = rental_match.group(1)
            self.logger.info(f"✓ Mietdauer extrahiert: {self.max_rental_period} Tage")
        else:
            self.max_rental_period = "6"
            self.logger.warning(f"⚠️ Mietdauer nicht gefunden, nutze Standard: {self.max_rental_period} Tage")

        yield from self.category_requests()

    def agb_failed(self, failure):
        """AGB nicht erreichbar — mit Standardwert weiterarbeiten."""
        self.max_rental_period = "6"
        self.logger.warning(f"⚠️ AGB nicht abrufbar ({failure.value}), nutze Standard: 6 Tage")

        for request in self.category_requests():
            yield request

    def category_requests(self):
        for url, display_name in self.waste_type_urls:
            yield Request(
                url=url,
                callback=self.parse_category,
                meta={'waste_type': display_name},
            )

    def parse_category(self, response):
        """Sammelt die Produktlinks einer Abfallart."""
        waste_type = response.meta['waste_type']
        self.logger.info(f"--- Verarbeite: {waste_type} ---")

        product_links = []
        for href in response.css('a.product-name::attr(href)').getall():
            url = response.urljoin(href)
            if url not in product_links:
                product_links.append(url)

        if not product_links:
            self.logger.warning("  ⚠️ Keine Produkt-Links gefunden")
            return

        self.logger.info(f"  Gefunden: {len(product_links)} Produkte")

        for url in product_links:
            yield Request(
                url=url,
                callback=self.parse_product,
                meta={'waste_type': waste_type},
            )

    def parse_product(self, response):
        """Extrahiert Produktdetails von der Produktseite."""
        waste_type = response.meta['waste_type']

        # Größe aus dem Seitentitel: "... - 1,5 m³ | 2"
        page_title = ' '.join((response.css('title::text').get() or '').split())
        size = ""
        size_match = re.search(r'(\d+(?:[.,]\d+)?)\s*m³', page_title)
        if size_match:
            size = size_match.group(1).replace(',', '.')

        # Grundpreis: <p class="product-detail-price">342,99 €</p>
        price = self.clean_price(response.css('p.product-detail-price::text').get())

        # Deckelpreis: Options-Block mit der Überschrift "Mit Deckel"
        lid_price = ""
        for option in response.css('.option'):
            option_text = ' '.join(option.css('::text').getall())
            if 'Mit Deckel' in option_text:
                lid_price = self.clean_price(option.css('.price::text').get())
                break

        if not size or not price:
            self.logger.warning(f"⚠️ Größe oder Preis nicht gefunden für {response.url}")
            return

        self.total_products += 1
        self.logger.info(f"  ✓ {size}m³: {price}€ (Deckel: {lid_price}€)")

        yield {
            "source": "ORES Containerlogistik",
            "title": f"{size} m³ {waste_type}",
            "type": waste_type,
            "city": "Berlin",
            "size": size,
            "price": price,
            "lid_price": lid_price,
            "arrival_price": "Abhängig v. d. Zone 4€,6€,10€,12€",
            "departure_price": "inklusive",
            "max_rental_period": self.max_rental_period or "6",
            "fee_after_max": "",
            "cancellation_fee": "109,48",
            "URL": response.url
        }

    def closed(self, reason):
        self.logger.info("=" * 80)
        self.logger.info(f"✓ Gesamt gescrapt: {self.total_products} Produkte")
        self.logger.info("=" * 80)

    @staticmethod
    def page_text(response):
        """Sichtbarer Seitentext ohne Skript- und Style-Inhalte."""
        parts = response.xpath('//body//*[not(self::script or self::style)]/text()').getall()
        return re.sub(r'\s+', ' ', ' '.join(parts))

    @staticmethod
    def clean_price(raw):
        """'342,99 €' / '1.368,99 €' -> '342,99' / '1368,99'"""
        if not raw:
            return ""
        text = raw.replace('\xa0', ' ')
        match = re.search(r'([\d.,]+)\s*€', text)
        if not match:
            return ""
        value = match.group(1)
        # Tausenderpunkt entfernen, Komma als Dezimaltrenner behalten
        if '.' in value and ',' in value:
            value = value.replace('.', '')
        return value
