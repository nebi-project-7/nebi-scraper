"""
Silo-Zentrale Spider
Extrahiert Preise für Container-Entsorgung in Hamburg
PDF-Preisliste wird dynamisch gelesen und geparst.
Quelle: https://www.silozentrale.de/_files/ugd/f9c410_463ed3eac61e484fb93a5c889f54e077.pdf
"""

import io
import re
import requests
import pdfplumber

from scrapy import Spider


class SiloZentraleSpider(Spider):
    name = "silo-zentrale"
    allowed_domains = ["silozentrale.de"]
    start_urls = ["https://www.silozentrale.de/"]

    pdf_url = "https://www.silozentrale.de/_files/ugd/f9c410_463ed3eac61e484fb93a5c889f54e077.pdf"

    # Container-Größen (Spalten-Index in PDF-Tabelle)
    # Index: 2=3m³, 3=5m³, 4=7m³, 5=8m³, 6=10m³, 7=21m³, 8=25m³, 9=30m³
    size_columns = {
        2: "3",
        3: "5",
        4: "7",
        5: "8",
        6: "10",
        7: "21",
        8: "25",
        9: "30",
    }

    # Kategorien überspringen (Tonnage-basiert oder nicht relevant)
    skip_patterns = [
        "boden***",
        "boden/bauschutt",
        "boden / bauschutt",
        "tonnage",
        "abrechnung auf",
    ]

    def parse(self, response):
        self.log(f"\n{'='*80}")
        self.log(f"Starte Silo-Zentrale Scraping (PDF wird dynamisch gelesen)")
        self.log(f"{'='*80}\n")

        total_products = 0
        seen_products = set()  # Duplikat-Prüfung

        try:
            # PDF herunterladen
            self.log(f"📥 Lade PDF: {self.pdf_url}")
            pdf_response = requests.get(self.pdf_url, timeout=30)
            pdf_response.raise_for_status()

            # PDF parsen
            with pdfplumber.open(io.BytesIO(pdf_response.content)) as pdf:
                page = pdf.pages[0]
                tables = page.extract_tables()

                if not tables:
                    self.log("❌ Keine Tabellen in PDF gefunden")
                    return

                table = tables[0]
                self.log(f"✅ Tabelle mit {len(table)} Zeilen gefunden")

                # Tabelle verarbeiten (ab Zeile 1, Zeile 0 ist Header)
                current_category = None

                for row_idx, row in enumerate(table[1:], start=1):
                    if not row or len(row) < 10:
                        continue

                    category = row[0] if row[0] else current_category
                    subcategory = row[1] if row[1] else ""

                    # Kategorie merken für leere Zeilen
                    if row[0]:
                        current_category = row[0]

                    # Überspringen wenn Boden/Tonnage-basiert
                    if self._should_skip(category, subcategory):
                        continue

                    # Multi-line Zellen verarbeiten
                    subcategories = subcategory.split('\n') if subcategory else [""]

                    # Preise pro Spalte extrahieren (können auch multi-line sein)
                    prices_per_column = {}
                    for col_idx, size in self.size_columns.items():
                        if col_idx < len(row) and row[col_idx]:
                            cell_prices = str(row[col_idx]).split('\n')
                            prices_per_column[col_idx] = cell_prices

                    # Für jede Subcategory die Preise zuordnen
                    for sub_idx, subcat in enumerate(subcategories):
                        if not subcat.strip():
                            continue

                        waste_type = self._build_waste_type(category, subcat)
                        if not waste_type:
                            continue

                        self.log(f"\n--- {waste_type} ---")

                        for col_idx, size in self.size_columns.items():
                            if col_idx not in prices_per_column:
                                continue

                            cell_prices = prices_per_column[col_idx]
                            # Wähle den richtigen Preis für diese Subcategory
                            price_idx = min(sub_idx, len(cell_prices) - 1)
                            price = self._parse_price(cell_prices[price_idx])

                            if price:
                                # Duplikat-Prüfung
                                product_key = f"{waste_type}|{size}"
                                if product_key in seen_products:
                                    continue
                                seen_products.add(product_key)

                                total_products += 1
                                self.log(f"  ✓ {size}m³: {price}€")

                                yield {
                                    "source": "Silo-Zentrale",
                                    "title": f"{waste_type} {size} m³",
                                    "type": waste_type,
                                    "city": "Hamburg",
                                    "size": size,
                                    "price": price,
                                    "lid_price": None,
                                    "arrival_price": "inklusive",
                                    "departure_price": "inklusive",
                                    "max_rental_period": "28",
                                    "fee_after_max": "3,57",
                                    "cancellation_fee": "119,00",
                                    "URL": self.pdf_url
                                }

        except requests.RequestException as e:
            self.log(f"❌ Fehler beim PDF-Download: {e}")
        except Exception as e:
            self.log(f"❌ Fehler beim PDF-Parsing: {e}")
            import traceback
            self.log(traceback.format_exc())

        self.log(f"\n{'='*80}")
        self.log(f"✓ Gesamt gescrapt: {total_products} Produkte")
        self.log(f"{'='*80}\n")

    def _should_skip(self, category, subcategory):
        """Prüft ob Kategorie übersprungen werden soll."""
        combined = f"{category} {subcategory}".lower()
        return any(skip in combined for skip in self.skip_patterns)

    def _build_waste_type(self, category, subcategory):
        """Baut standardisierten Abfallart-Namen."""
        category = (category or "").strip()
        subcategory = (subcategory or "").strip()

        # Sternchen und Fußnoten entfernen
        category = re.sub(r'\*+', '', category).strip()
        subcategory = re.sub(r'\*+', '', subcategory).strip()

        # Spezielle Mappings
        cat_lower = category.lower()
        sub_lower = subcategory.lower()

        # Bauschutt/Beton
        if "bauschutt/beton" in cat_lower:
            if "sauber" in sub_lower:
                return "Bauschutt/Beton sauber"
            elif "verunreinigt" in sub_lower and "kantenlänge" not in sub_lower:
                return "Bauschutt/Beton verunreinigt"
            elif "50-100" in sub_lower:
                return "Bauschutt/Beton Kantenlänge 50-100 cm"
            elif "größer 100" in sub_lower or "100 cm" in sub_lower:
                return "Bauschutt/Beton Kantenlänge > 100 cm"

        # Baumischabfall
        if "baumischabfall" in cat_lower:
            if "mit wertstoffen" in sub_lower or "ohne mineralik" in sub_lower:
                return "Baumischabfall mit Wertstoffen"
            elif "verunreinigt" in sub_lower and "bauschutt" in sub_lower:
                return "Baumischabfall verunreinigt mit Bauschutt/Gips"
            elif "styropor" in sub_lower and "gemisch" in sub_lower:
                return "Baumischabfall mit Styropor"
            elif "nicht recyclebar" in sub_lower or "ohne wertstoffe" in sub_lower:
                return "Baumischabfall nicht recyclebar"

        # Styropor
        if "styropor" in cat_lower and "monocharg" in cat_lower:
            return "Styropor (EPS) sauber"

        # Leichtbaustoffe
        if "leichtbaustoffe" in cat_lower:
            return "Leichtbaustoffe (Ytong/Gips)"

        # Asbest
        if "asbest" in cat_lower:
            return "Asbest"

        # Holz
        if "holz" in cat_lower:
            if "a1" in sub_lower and "a3" in sub_lower:
                if "nicht belastet" in sub_lower:
                    return "Holz A1-A3"
                elif "verunreinigt" in sub_lower:
                    return "Holz A1-A3 verunreinigt"
            elif "a4" in sub_lower:
                return "Holz A4"

        # Sperrmüll
        if "sperrmüll" in cat_lower:
            return "Sperrmüll"

        # Gartenabfall
        if "gartenabfall" in cat_lower:
            if "strauchgut" in sub_lower or "baumschnitt" in sub_lower:
                return "Gartenabfälle (Strauchgut)"
            elif "laub" in sub_lower or "rasenschnitt" in sub_lower:
                return "Gartenabfälle (Laub/Rasen)"

        # Dachpappe
        if "dachpappe" in cat_lower:
            if "ohne fremdstoffe" in sub_lower:
                return "Dachpappe teerhaltig"
            elif "mit verunreinigung" in sub_lower:
                return "Dachpappe teerhaltig verunreinigt"

        # Papier + Pappe
        if "papier" in cat_lower and "pappe" in cat_lower:
            return "Papier/Pappe"

        # Folien
        if "folien" in cat_lower:
            return "Folien"

        # KMF-Dämmung
        if "kmf" in cat_lower or "dämmung" in cat_lower:
            return "KMF-Dämmung"

        return None

    def _parse_price(self, price_str):
        """Parst Preis-String zu deutschem Format."""
        if not price_str:
            return None

        price_str = str(price_str).strip()

        # Leere oder ungültige Werte
        if price_str in ['XXX', '-', '–', '', 'None', '- " -']:
            return None

        if 'abrechnung' in price_str.lower() or 'tonnage' in price_str.lower():
            return None

        # Zahlen extrahieren
        clean = re.sub(r'[^\d.,]', '', price_str)

        if not clean:
            return None

        # Deutsche Format-Konvertierung (1.234,56 → 1234,56)
        # PDF verwendet deutsches Format mit Punkt als Tausender-Trenner
        if ',' in clean and '.' in clean:
            # Deutsches Format: 1.234,56
            clean = clean.replace('.', '')
        elif '.' in clean:
            # Könnte Tausender-Punkt sein (1.234) oder Dezimal-Punkt (123.45)
            parts = clean.split('.')
            if len(parts) == 2 and len(parts[1]) == 2:
                # Wahrscheinlich Dezimal-Punkt → zu Komma
                clean = clean.replace('.', ',')
            else:
                # Tausender-Punkt entfernen
                clean = clean.replace('.', '')

        return clean if clean else None
