"""
Platz-Meister Spider
Extrahiert Preise für Container-Entsorgung in Stuttgart
Website: https://containerdienst.platz-meister.de/preise-containerdienst/
"""

import re
from scrapy import Spider


class PlatzMeisterSpider(Spider):
    name = "platz-meister"
    allowed_domains = ["containerdienst.platz-meister.de"]
    start_urls = ["https://containerdienst.platz-meister.de/preise-containerdienst/"]

    # Abfallarten die übersprungen werden sollen
    SKIP_WASTE_TYPES = [
        'Fenster-Altholz A IV',
    ]

    # Mapping von Website-Namen zu standardisierten Abfalltypen
    waste_type_mapping = {
        'Erde unbelastet': 'Erde unbelastet',
        'Bauschutt-Erde-Gemischt': 'Bauschutt-Erde-Gemisch',
        'Metallschrott': 'Metallschrott',
        'Gewerbeabfall': 'Gewerbeabfälle',
        'Sperrmüll': 'Sperrmüll',
        'Siedlungsabfall / Restmüll': 'Siedlungsabfall',
        'Flachglas': 'Flachglas',
        'Erdaushub': 'Erdaushub',
        'Bauschutt / Beton': 'Bauschutt',
        'Holz A4': 'Holz A4',
        'Baumischabfall': 'Baumischabfall',
        'Altpapier': 'Papier/Pappe',
        'Altholz': 'Holz A1-A3',
    }

    def parse(self, response):
        self.log(f"\n{'='*80}")
        self.log(f"Starte Platz-Meister Scraping für Stuttgart")
        self.log(f"{'='*80}\n")

        total_products = 0

        # Tabelle finden
        table = response.css('table')
        if not table:
            self.log("FEHLER: Keine Tabelle gefunden")
            return

        # Header-Zeile für Größen (verschachtelte DIV-Struktur)
        header_row = table.css('tr:first-child')
        header_cells = header_row.css('th')
        sizes = []
        for cell in header_cells[1:]:  # Skip "Abfallart"
            # Text aus verschachtelter Struktur extrahieren
            text = cell.css('.jet-table__cell-text::text').get()
            if not text:
                text = cell.css('::text').get()
            if text:
                sizes.append(text.strip())

        self.log(f"Gefundene Größen: {sizes}")

        # Daten-Zeilen
        rows = table.css('tr')[1:]  # Skip header

        for row in rows:
            cells = row.css('td')
            if not cells:
                continue

            # Erste Zelle ist Abfallart (verschachtelte Struktur)
            waste_type_raw = cells[0].css('.jet-table__cell-text::text').get()
            if not waste_type_raw:
                waste_type_raw = cells[0].css('::text').get()
            if not waste_type_raw:
                continue
            waste_type_raw = waste_type_raw.strip()

            # Überspringe bestimmte Abfallarten
            if waste_type_raw in self.SKIP_WASTE_TYPES:
                self.log(f"\n--- Überspringe: {waste_type_raw} ---")
                continue

            # Mapping anwenden
            waste_type = self.waste_type_mapping.get(waste_type_raw, waste_type_raw)

            self.log(f"\n--- {waste_type_raw} -> {waste_type} ---")

            # Preise für jede Größe
            for i, cell in enumerate(cells[1:]):
                if i >= len(sizes):
                    break

                # Text aus verschachtelter Struktur
                price_text = cell.css('.jet-table__cell-text::text').get()
                if not price_text:
                    price_text = cell.css('::text').get()
                if not price_text:
                    continue
                price_text = price_text.strip()

                # Überspringe wenn kein Preis verfügbar
                if price_text == '–' or price_text == '-' or not price_text:
                    continue

                # Preis extrahieren (z.B. "455 €" oder "1.250 €")
                price_match = re.search(r'([\d.]+)\s*€', price_text)
                if not price_match:
                    continue

                # Preis formatieren (Tausendertrennzeichen entfernen, Komma für Dezimal)
                price_value = price_match.group(1).replace('.', '')
                price = f"{price_value},00"

                # Größe
                size = sizes[i].replace('m³', ' m³')

                # Produkt erstellen
                product = {
                    "source": "Platz-Meister",
                    "title": f"{size} {waste_type}",
                    "type": waste_type,
                    "city": "Stuttgart",
                    "size": size,
                    "price": price,
                    "lid_price": None,
                    "arrival_price": "inklusive",
                    "departure_price": "inklusive",
                    "max_rental_period": "14 Tage",
                    "fee_after_max": "30,00 EUR/Woche",
                    "cancellation_fee": None,
                    "URL": response.url
                }

                total_products += 1
                self.log(f"  ✓ {size}: {price} EUR")
                yield product

        self.log(f"\n{'='*80}")
        self.log(f"Gesamt gescrapt: {total_products} Produkte")
        self.log(f"{'='*80}\n")
