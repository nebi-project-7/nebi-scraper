"""
Container NRW Spider
Extrahiert Preise für Container-Entsorgung in Köln
Shop: http://www.containernrw.de/container_koeln_rechts.html
"""

import re
from scrapy import Spider


class ContainerNrwSpider(Spider):
    name = "container-nrw"
    allowed_domains = ["containernrw.de"]
    start_urls = ["http://www.containernrw.de/container_koeln_rechts.html"]

    # Abfallarten in der Reihenfolge wie auf der Website
    # (Pattern zum Erkennen, Standardisierter Name)
    # WICHTIG: Manche Abfallarten sind über mehrere Paragraphen verteilt
    waste_types_ordered = [
        (r'Baumischabfall.*?10%.*?Mineralik', "Baumischabfall 10% Mineralik"),
        (r'keine\s*Mineralik.*?Rigips', "Baumischabfall keine Mineralik"),  # "keine Mineralik ausser Rigips" in separatem <p>
        (r'Bauschutt\s*sauber', "Bauschutt sauber"),
        (r'^Rigips\s*ohne', "Rigips"),  # "Rigips ohne Tapeten..."
        (r'Holz\s*Bau-?\s*und\s*Abbruchholz', "Bau- und Abbruchholz"),
        (r'Porenbeton|Bauschutt\s*verunreinigt', "Bauschutt verunreinigt"),
        (r'Sperrmüll\s*oder', "Sperrmüll"),
        (r'^Gartenabfall', "Gartenabfälle"),
        (r'^Erdaushub\s*$', "Erdaushub sauber"),  # Nur "Erdaushub" als Text
        (r'Erde\s*\+\s*Steine', "Erde + Steine"),
    ]

    def parse(self, response):
        self.log(f"\n{'='*80}")
        self.log(f"Starte Container NRW Scraping (Köln)")
        self.log(f"{'='*80}\n")

        standzeit = "7"  # 1 Woche
        fee_after_max = "10,00"  # 10€ pro Woche

        products = []
        seen_products = set()

        # Alle Paragraphen extrahieren (behält Reihenfolge)
        all_paragraphs = response.css("p")

        # Text aus allen Paragraphen sammeln
        texts = []
        for p in all_paragraphs:
            text = ' '.join(p.css("*::text").getall()).strip()
            text = re.sub(r'\s+', ' ', text)
            if text:
                texts.append(text)

        # Finde Abfallarten und ihre Positionen
        waste_positions = []
        for i, text in enumerate(texts):
            for pattern, waste_type in self.waste_types_ordered:
                if re.search(pattern, text, re.I):
                    # Prüfe ob es nicht Teil einer Preis/Größen-Zeile ist
                    if 'cbm' not in text.lower() and '€' not in text:
                        waste_positions.append((i, waste_type))
                        break

        # Für jede gefundene Abfallart, extrahiere Preise bis zur nächsten Abfallart
        for idx, (pos, waste_type) in enumerate(waste_positions):
            self.log(f"\n--- Verarbeite: {waste_type} ---")

            # Ende-Position bestimmen (nächste Abfallart oder Ende)
            end_pos = waste_positions[idx + 1][0] if idx + 1 < len(waste_positions) else len(texts)

            # Extrahiere Größen und Preise zwischen pos und end_pos
            pending_size = None

            for text in texts[pos:end_pos]:
                # Größe finden (ignoriere 4 cbm)
                size_match = re.match(r'^(\d+)\s*cbm\*?$', text.strip(), re.I)
                if size_match:
                    size = size_match.group(1)
                    if size != "4":  # 4 cbm nur für Langenfeld etc.
                        pending_size = size
                    continue

                # Preis finden (Brutto = endet auf ,00)
                price_match = re.match(r'^([\d.]+,00)\s*€?$', text.strip())
                if price_match and pending_size:
                    price = price_match.group(1)

                    # Tausender-Trennzeichen entfernen
                    if '.' in price and ',' in price:
                        price = price.replace('.', '')

                    price_val = float(price.replace(',', '.'))

                    # Plausibilitätscheck (> 200€)
                    if price_val >= 200:
                        product_key = f"{waste_type}|{pending_size}"

                        if product_key not in seen_products:
                            seen_products.add(product_key)

                            product = {
                                "source": "Container NRW",
                                "title": f"{waste_type} {pending_size} m³",
                                "type": waste_type,
                                "city": "Köln",
                                "size": pending_size,
                                "price": price,
                                "lid_price": "nur wenn vorrätig",
                                "arrival_price": "inklusive",
                                "departure_price": "inklusive",
                                "max_rental_period": standzeit,
                                "fee_after_max": fee_after_max,
                                "cancellation_fee": None,
                                "URL": response.url
                            }
                            products.append(product)
                            self.log(f"  ✓ {pending_size}m³: {price}€")

                    pending_size = None

        # Produkte ausgeben
        for product in products:
            yield product

        self.log(f"\n{'='*80}")
        self.log(f"✓ Gesamt gescrapt: {len(products)} Produkte")
        self.log(f"{'='*80}\n")
