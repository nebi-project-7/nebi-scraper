"""
DER HAMBURG CONTAINER Spider
Extrahiert Preise für Container-Entsorgung in Hamburg
Shop: https://der-hamburg-container.de/
"""

import re
from scrapy import Spider, Request


class DerHamburgContainerSpider(Spider):
    name = "der-hamburg-container"
    allowed_domains = ["der-hamburg-container.de"]
    start_urls = ["https://der-hamburg-container.de/abfallbibel/"]

    # Kategorien mit ihren URLs und standardisierten Namen
    waste_categories = [
        ("bauschutt-entsorgen", "Bauschutt"),
        ("baumischabfaelle-entsorgen", "Baumischabfall"),
        ("holz-a1-a3-entsorgen", "Holz A1-A3"),
        ("holz-a4-entsorgen", "Holz A4"),
        ("sperrmuell-entsorgen", "Sperrmüll"),
        ("gartenabfall-entsorgen", "Gartenabfälle"),  # Immer "Gartenabfälle"
        ("gips-entsorgen", "Gips"),
        ("boden-und-steine-entsorgen", "Boden"),
        ("dachpappe-entsorgen", "Dachpappe"),
        # ("asbest-entsorgen", "Asbest"),  # Oft nur auf Anfrage
        ("glaswolle-steinwolle-entsorgen", "Dämmstoffe"),
        # ("metall-entsorgen", "Schrott"),  # Meist kostenlos/Ankauf
    ]

    def __init__(self):
        self.seen_products = set()

    def parse(self, response):
        """Startet das Crawling aller Kategorien."""
        self.log(f"\n{'='*80}")
        self.log(f"Starte DER HAMBURG CONTAINER Scraping")
        self.log(f"{'='*80}\n")

        for category_slug, waste_type in self.waste_categories:
            category_url = f"https://der-hamburg-container.de/{category_slug}/"
            yield Request(
                url=category_url,
                callback=self.parse_category,
                meta={'waste_type': waste_type}
            )

    def parse_category(self, response):
        """Extrahiert alle Produkte von einer Kategorieseite."""
        waste_type = response.meta['waste_type']
        self.log(f"\n--- Verarbeite: {waste_type} ---")

        # Finde alle Produkt-Boxen
        products = response.css('.product, .product-small')

        if not products:
            # Alternative Selektor
            products = response.xpath('//div[contains(@class, "product")]')

        product_count = 0

        for product in products:
            try:
                # Titel extrahieren
                title = product.css('.product_title::text, .woocommerce-loop-product__title::text').get()
                if not title:
                    title = product.css('h2::text').get()
                if not title:
                    title = product.xpath('.//h2//text()').get()

                if not title:
                    continue

                title = title.strip()

                # Überspringe BigBags
                if 'bag' in title.lower() or 'big' in title.lower():
                    continue

                # Extrahiere Größe aus Titel (z.B. "3 m³ Absetzmulde für Bauschutt")
                size_match = re.search(r'(\d+)\s*m[³3]', title)
                if not size_match:
                    continue

                size = size_match.group(1)

                # Preis extrahieren
                price_text = product.css('.woocommerce-Price-amount bdi::text').get()
                if not price_text:
                    price_text = product.css('.price .amount::text').get()
                if not price_text:
                    # Versuche aus dem gesamten Preis-Element
                    price_elem = product.css('.price').get()
                    if price_elem:
                        price_match = re.search(r'(\d+(?:\.\d{3})*(?:,\d{2})?)', price_elem)
                        if price_match:
                            price_text = price_match.group(1)

                if not price_text:
                    continue

                # Preis bereinigen (z.B. "279,00" → "279")
                price_clean = price_text.replace('.', '').replace(',00', '').replace(',', '')
                # Entferne führende Nullen und Dezimalstellen
                price_match = re.search(r'(\d+)', price_clean)
                if price_match:
                    price = price_match.group(1)
                else:
                    continue

                # URL extrahieren - nur /produkt/ Links akzeptieren
                all_links = product.css('a::attr(href)').getall()
                product_url = None
                for link in all_links:
                    if '/produkt/' in link:
                        product_url = link
                        break
                # Fallback: Kategorie-URL statt Liefergebiet
                if not product_url:
                    product_url = response.url

                # Duplikat-Check
                product_key = f"{waste_type}|{size}"
                if product_key in self.seen_products:
                    continue
                self.seen_products.add(product_key)

                product_count += 1
                self.log(f"  ✓ {size}m³: {price}€")

                yield {
                    "source": "Der Hamburg Container",
                    "title": f"{waste_type} {size} m³",
                    "type": waste_type,
                    "city": "Hamburg",
                    "size": size,
                    "price": price,
                    "lid_price": None,
                    "arrival_price": "inklusive",
                    "departure_price": "inklusive",
                    "max_rental_period": "7",
                    "fee_after_max": None,
                    "cancellation_fee": None,
                    "URL": product_url
                }

            except Exception as e:
                self.log(f"  ⚠️ Fehler beim Parsen: {e}")
                continue

        self.log(f"  ✓ {product_count} Produkte extrahiert")
