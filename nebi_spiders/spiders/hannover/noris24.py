"""
Noris24 Spider
Extrahiert Preise für Container-Entsorgung in Hannover
Shop: https://www.noris24.de/containeruebersicht/
"""

import re
from scrapy import Spider, Request


class Noris24Spider(Spider):
    name = "noris24"
    allowed_domains = ["noris24.de"]
    start_urls = ["https://www.noris24.de/containeruebersicht/"]

    # 11 Abfallarten (URL-Slug -> Standardisierter Name)
    # Ignoriere: BigBags, Säcke
    waste_categories = [
        ("baumischabfall", "Baumischabfall"),
        ("sperrmuell", "Sperrmüll"),
        ("bauschutt", "Bauschutt"),
        ("gruenschnitt", "Grünschnitt"),
        ("mischholz-container", "Holz unbehandelt"),
        ("a4-holz-container", "Holz imprägniert"),
        ("daemmstoffcontainer", "Dämmstoffe"),
        ("gips", "Gips"),
        ("altmetall-schrott", "Altmetall"),
        ("bodenbauschuttcontainer", "Boden mit Bauschutt"),
        ("bodencontainer", "Boden"),
    ]

    def __init__(self):
        self.seen_products = set()

    def parse(self, response):
        self.log(f"\n{'='*80}")
        self.log(f"Starte Noris24 Scraping (Hannover)")
        self.log(f"{'='*80}\n")

        # Für jede Abfallart eine Anfrage starten
        for url_slug, waste_type in self.waste_categories:
            category_url = f"https://www.noris24.de/{url_slug}/"
            yield Request(
                url=category_url,
                callback=self.parse_category,
                meta={"waste_type": waste_type, "url_slug": url_slug}
            )

    def parse_category(self, response):
        waste_type = response.meta["waste_type"]
        self.log(f"\n--- Verarbeite: {waste_type} ---")

        # Finde alle Produkt-Links auf der Kategorie-Seite
        product_links = response.css("a.woocommerce-LoopProduct-link::attr(href)").getall()

        if not product_links:
            # Alternative Selektoren versuchen
            product_links = response.css("a[href*='/produkt/']::attr(href)").getall()

        if not product_links:
            # Fallback: Alle Links die auf /produkt/ zeigen
            all_links = response.css("a::attr(href)").getall()
            product_links = [l for l in all_links if "/produkt/" in l]

        # Duplikate entfernen
        product_links = list(set(product_links))

        self.log(f"  Gefunden: {len(product_links)} Produkte")

        for product_url in product_links:
            # BigBags und Säcke überspringen
            if "bigbag" in product_url.lower() or "sack" in product_url.lower():
                continue

            yield Request(
                url=response.urljoin(product_url),
                callback=self.parse_product,
                meta={"waste_type": waste_type}
            )

    def parse_product(self, response):
        waste_type = response.meta["waste_type"]

        try:
            # Produkttitel extrahieren - Seite ist JS-gerendert, daher aus og:title
            title = response.css("meta[property='og:title']::attr(content)").get()
            if not title:
                title = response.css("title::text").get()

            if not title:
                return

            title = title.strip()
            # " - Noris Entsorgung GmbH" entfernen
            title = re.sub(r'\s*-\s*Noris.*$', '', title)

            # BigBags und Säcke überspringen
            if "bigbag" in title.lower() or "sack" in title.lower():
                return

            # Größe aus Titel extrahieren (z.B. "1,5 m³", "10 m³", "35 m³")
            size_match = re.search(r'(\d+[,.]?\d*)\s*m[³³]', title, re.I)
            if not size_match:
                return

            size_raw = size_match.group(1)
            # Komma zu Punkt für einheitliche Darstellung
            size = size_raw.replace(',', '.')

            # Preis extrahieren - aus Meta-Tag (product:price:amount)
            price = None
            price_meta = response.css("meta[property='product:price:amount']::attr(content)").get()
            if price_meta:
                # Preis als Zahl, in deutsches Format konvertieren
                try:
                    price_val = float(price_meta)
                    if price_val == int(price_val):
                        price = f"{int(price_val)},00"
                    else:
                        price = f"{price_val:.2f}".replace('.', ',')
                except ValueError:
                    pass

            if not price:
                # Fallback: Aus Twitter-Meta extrahieren
                twitter_price = response.css("meta[name='twitter:data1']::attr(content)").get()
                if twitter_price:
                    price_match = re.search(r'([\d.,]+)', twitter_price)
                    if price_match:
                        price = price_match.group(1).replace('.', '').replace('&nbsp;', '')

            if not price:
                # Fallback: WooCommerce Preis-Element
                price_elem = response.css("p.price bdi::text, p.price span.amount::text").get()
                if price_elem:
                    price_match = re.search(r'([\d.,]+)', price_elem)
                    if price_match:
                        price = price_match.group(1)
                        if '.' in price and ',' in price:
                            price = price.replace('.', '')

            if not price:
                return

            # Produkt-Key für Deduplizierung
            product_key = f"{waste_type}|{size}"
            if product_key in self.seen_products:
                return
            self.seen_products.add(product_key)

            product = {
                "source": "Noris24",
                "title": f"{waste_type} {size} m³",
                "type": waste_type,
                "city": "Hannover",
                "size": size,
                "price": price,
                "lid_price": None,
                "arrival_price": "inklusive",
                "departure_price": "inklusive",
                "max_rental_period": "45",
                "fee_after_max": "1,00",
                "cancellation_fee": None,
                "URL": response.url
            }

            self.log(f"  ✓ {size}m³: {price}€")
            yield product

        except Exception as e:
            self.log(f"  ⚠️ Fehler bei Produkt: {e}")
