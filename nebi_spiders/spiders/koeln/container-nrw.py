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

    # Mapping der Abfallarten zur Standardisierung
    # Die Website hat komplexe Beschreibungen, die wir vereinfachen
    waste_type_mapping = {
        "baumischabfall": "Baumischabfall",
        "bauschutt sauber": "Bauschutt",
        "bauschutt verunreinigt": "Bauschutt verunreinigt",
        "porenbeton": "Bauschutt verunreinigt",
        "rigips": "Gips",
        "holz": "Altholz",
        "abbruchholz": "Altholz",
        "sperrmüll": "Sperrmüll",
        "gemischte abfälle": "Sperrmüll",
        "gartenabfall": "Gartenabfälle",
        "grünschnitt": "Gartenabfälle",
        "erde": "Boden",
    }

    def parse(self, response):
        self.log(f"\n{'='*80}")
        self.log(f"Starte Container NRW Scraping (Köln)")
        self.log(f"{'='*80}\n")

        # Extrahiere Standzeit aus dem Text
        standzeit_text = response.xpath("//p[contains(text(), 'Standzeit')]//text()").getall()
        standzeit = "7"  # Default: 1 Woche
        fee_after_max = "10,00"  # 10€ pro Woche

        # Alle Tabellenzellen extrahieren
        # Die Seite nutzt eine Tabelle mit komplexer Struktur
        table = response.css("table")

        if not table:
            self.log("⚠️ Keine Tabelle gefunden, versuche Text-Parsing")
            yield from self._parse_from_text(response)
            return

        # Extrahiere alle Zeilen
        rows = table.css("tr")

        products = []
        current_waste_type = None
        seen_products = set()

        for row in rows:
            cells = row.css("td")
            if not cells:
                continue

            # Extrahiere Text aus allen Zellen
            cell_texts = []
            for cell in cells:
                text = ' '.join(cell.css("*::text").getall()).strip()
                text = re.sub(r'\s+', ' ', text)
                cell_texts.append(text)

            # Suche nach Abfallart in der Zeile
            row_text = ' '.join(cell_texts).lower()

            # Prüfe ob es eine Abfallart-Zeile ist
            for key, waste_type in self.waste_type_mapping.items():
                if key in row_text and 'cbm' not in row_text and '€' not in row_text:
                    current_waste_type = waste_type
                    self.log(f"\n--- Verarbeite: {waste_type} ---")
                    break

            # Suche nach Größe und Preis
            for text in cell_texts:
                # Größe finden (ignoriere 4 cbm - nur für bestimmte Gebiete außerhalb Köln)
                size_match = re.search(r'^(\d+)\s*cbm\*?$', text.strip(), re.I)
                if size_match:
                    size = size_match.group(1)

                    # 4 cbm überspringen (nur für Langenfeld etc., nicht Köln)
                    if size == "4":
                        continue

                    # Preis in der nächsten Zelle suchen
                    for other_text in cell_texts:
                        price_match = re.search(r'^([\d.,]+)\s*€$', other_text.strip())
                        if price_match and current_waste_type:
                            price = price_match.group(1)

                            # Prüfe ob es Brutto-Preis ist (höherer Wert)
                            price_val = float(price.replace(',', '.'))

                            # Nur Brutto-Preise (die höheren) verwenden
                            if price_val > 200:  # Plausibilitätscheck
                                product_key = f"{current_waste_type}|{size}"

                                if product_key not in seen_products:
                                    seen_products.add(product_key)

                                    product = {
                                        "source": "Container NRW",
                                        "title": f"{current_waste_type} {size} m³",
                                        "type": current_waste_type,
                                        "city": "Köln",
                                        "size": size,
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

        # Falls Tabellen-Parsing nicht funktioniert, Text-Parsing versuchen
        if not products:
            self.log("⚠️ Tabellen-Parsing ergab keine Ergebnisse, versuche Text-Parsing")
            yield from self._parse_from_text(response)
            return

        # Produkte ausgeben
        for product in products:
            self.log(f"  ✓ {product['type']} {product['size']}m³: {product['price']}€")
            yield product

        self.log(f"\n{'='*80}")
        self.log(f"✓ Gesamt gescrapt: {len(products)} Produkte")
        self.log(f"{'='*80}\n")

    def _parse_from_text(self, response):
        """Fallback: Extrahiert Preise aus dem reinen Text der Seite."""

        products = []
        seen_products = set()

        # Alle Text-Elemente extrahieren (behält die Reihenfolge)
        all_texts = response.css("p::text, span::text, td::text").getall()
        all_texts = [t.strip() for t in all_texts if t.strip()]

        # Definiere die Abfallarten-Patterns
        waste_patterns = [
            (r'Baumischabfall.*?10%.*?Mineralik', "Baumischabfall"),
            (r'Baumischabfall.*?keine.*?Mineralik', "Baumischabfall leicht"),
            (r'Bauschutt\s*sauber', "Bauschutt"),
            (r'Rigips', "Gips"),
            (r'Holz|Abbruchholz', "Altholz"),
            (r'Porenbeton|Bauschutt.*?verunreinigt', "Bauschutt verunreinigt"),
            (r'Sperrmüll|gemischte\s*Abfälle', "Sperrmüll"),
            (r'Gartenabfall|Grünschnitt', "Gartenabfälle"),
            (r'Erde.*?Steine', "Boden"),
        ]

        current_waste_type = None
        pending_size = None

        for i, text in enumerate(all_texts):
            text_clean = re.sub(r'\s+', ' ', text)

            # Prüfe auf Abfallart
            for pattern, waste_type in waste_patterns:
                if re.search(pattern, text_clean, re.I):
                    # Nur setzen wenn es nicht Teil einer Größen/Preis-Zeile ist
                    if 'cbm' not in text_clean.lower() and '€' not in text_clean:
                        current_waste_type = waste_type
                    break

            # Prüfe auf Größe
            size_match = re.match(r'^(\d+)\s*cbm\*?$', text_clean, re.I)
            if size_match:
                size = size_match.group(1)
                # 4 cbm überspringen
                if size != "4":
                    pending_size = size
                continue

            # Prüfe auf Preis (Brutto-Preis mit Komma)
            price_match = re.match(r'^([\d.]+,\d{2})\s*€?$', text_clean)
            if price_match and pending_size and current_waste_type:
                price = price_match.group(1)

                # Tausender-Trennzeichen entfernen
                if '.' in price and ',' in price:
                    price = price.replace('.', '')

                price_val = float(price.replace(',', '.'))

                # Nur Brutto-Preise (typischerweise der erste/höhere Wert)
                # Netto-Preise haben meist Nachkommastellen wie ,52 ,36 etc.
                if price_val >= 200 and price.endswith(',00'):
                    product_key = f"{current_waste_type}|{pending_size}"

                    if product_key not in seen_products:
                        seen_products.add(product_key)

                        product = {
                            "source": "Container NRW",
                            "title": f"{current_waste_type} {pending_size} m³",
                            "type": current_waste_type,
                            "city": "Köln",
                            "size": pending_size,
                            "price": price,
                            "lid_price": "nur wenn vorrätig",
                            "arrival_price": "inklusive",
                            "departure_price": "inklusive",
                            "max_rental_period": "7",
                            "fee_after_max": "10,00",
                            "cancellation_fee": None,
                            "URL": response.url
                        }
                        products.append(product)
                        self.log(f"  ✓ {current_waste_type} {pending_size}m³: {price}€")

                pending_size = None

        self.log(f"\n{'='*80}")
        self.log(f"✓ Gesamt gescrapt: {len(products)} Produkte")
        self.log(f"{'='*80}\n")

        for product in products:
            yield product
