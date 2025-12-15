"""
ABC Container Spider
Extrahiert Preise für Container-Entsorgung in Hamburg
PDF-Preisliste wird dynamisch gelesen und geparst.
Quelle: https://abccontainer.de/wp-content/uploads/2025-04-Preisliste-Container1.pdf
"""

import io
import re
import requests
import pdfplumber

from scrapy import Spider


class ABCContainerHamburgSpider(Spider):
    name = "abc-container-hamburg"
    allowed_domains = ["abccontainer.de"]
    start_urls = ["https://abccontainer.de/"]

    pdf_url = "https://abccontainer.de/wp-content/uploads/2025-04-Preisliste-Container1.pdf"

    # Container-Größen (Spalten-Index in PDF-Tabelle)
    # Index 0=Abfallart, 1=BigBag, 2=1m³, 3=6m³, 4=10m³, 5=14m³, 6=25m³, 7=30m³, 8=LKW
    size_columns = {
        2: "1",
        3: "6",
        4: "10",
        5: "14",
        6: "25",
        7: "30",
    }

    # Mapping: PDF-Text → Standardisierter Name
    # WICHTIG: Spezifischere Patterns MÜSSEN vor allgemeineren stehen!
    waste_type_mapping = [
        # Baustellenabfälle - spezifische zuerst
        ("baustellenabfälle/ bauschutt verunreinigt", "Baustellenabfälle/ Bauschutt verunreinigt durch Bauschutt/ Gips"),
        ("baustellenabfälle nicht recycelbar", "Baustellenabfälle nicht recycelbar"),
        ("baustellenabfälle", "Baustellenabfälle ohne Bauschutt/ Gips"),
        # Rest
        ("bauschutt sauber", "Bauschutt sauber"),
        ("beton< 50 cm", "Beton < 50 cm"),
        ("beton < 50 cm", "Beton < 50 cm"),
        ("boden mit wurzeln, soden + grasnaben", "Boden mit Wurzeln, Soden + Grasnaben"),
        ("boden mit wurzeln", "Boden mit Wurzeln, Soden + Grasnaben"),
        ("sperrmüll", "Sperrmüll"),
        ("holz a1-a3", "Holz A1-A3"),
        ("holz a4", "Holz A4"),
        ("gartenabfälle 1", "Gartenabfälle 1 Strauchgut, Baumschnitt"),
        ("gartenabfälle 2", "Gartenabfälle 2 Laub- und Grasschnitt"),
        ("subben & stammholz", "Subben & Stammholz"),
        ("stubben & stammholz", "Subben & Stammholz"),
        ("dachpappe", "Dachpappe"),
    ]

    # Kategorien überspringen (BigBag-only und andere Boden-Arten)
    skip_categories = [
        "kmf-dämmstoffe",
        "kmf-deckenplatten",
        "odenwaldplatten",
        "styropor",
        "boden bis 20m³",
        "boden über 20m³",
    ]

    def parse(self, response):
        self.log(f"\n{'='*80}")
        self.log(f"Starte ABC Container Scraping (PDF wird dynamisch gelesen)")
        self.log(f"{'='*80}\n")

        total_products = 0
        cancellation_fee = "101,15"  # Default: 85€ netto = 101,15€ brutto

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

                # Fehlfahrt-Preis aus PDF extrahieren
                text = page.extract_text()
                if text:
                    fehlfahrt_match = re.search(r'Fehlfahrten.*?(\d+)[,.\-]\s*€', text)
                    if fehlfahrt_match:
                        netto = float(fehlfahrt_match.group(1))
                        brutto = netto * 1.19
                        cancellation_fee = f"{brutto:.2f}".replace('.', ',')
                        self.log(f"📋 Fehlfahrt: {netto}€ netto = {cancellation_fee}€ brutto")

                # Tabelle verarbeiten (Zeilen paarweise: Netto + Brutto)
                current_waste_type = None
                i = 0

                while i < len(table):
                    row = table[i]

                    # Zeile mit Abfallart-Name (erste Spalte nicht None/leer)
                    if row[0] and str(row[0]).strip():
                        waste_name_raw = str(row[0]).strip()
                        # Newlines entfernen, nur erste Zeile nehmen
                        waste_name_raw = waste_name_raw.split('\n')[0].strip()
                        current_waste_type = self._standardize_waste_type(waste_name_raw)

                        # Überspringen wenn BigBag-only oder nicht gemappt
                        if not current_waste_type or self._should_skip(waste_name_raw):
                            i += 2  # Netto + Brutto überspringen
                            continue

                        # Nächste Zeile sollte Brutto-Preise haben
                        if i + 1 < len(table):
                            brutto_row = table[i + 1]

                            # Brutto-Zeile hat None in erster Spalte
                            if brutto_row[0] is None or not str(brutto_row[0]).strip():
                                self.log(f"\n--- {current_waste_type} ---")

                                for col_idx, size in self.size_columns.items():
                                    if col_idx < len(brutto_row):
                                        price = self._parse_price(brutto_row[col_idx])
                                        if price:
                                            total_products += 1
                                            self.log(f"  ✓ {size}m³: {price}€")

                                            yield {
                                                "source": "ABC Container",
                                                "title": f"{current_waste_type} {size} m³",
                                                "type": current_waste_type,
                                                "city": "Hamburg",
                                                "size": size,
                                                "price": price,
                                                "lid_price": None,
                                                "arrival_price": "inklusive",
                                                "departure_price": "inklusive",
                                                "max_rental_period": None,
                                                "fee_after_max": None,
                                                "cancellation_fee": cancellation_fee,
                                                "URL": self.pdf_url
                                            }

                            i += 2  # Netto + Brutto verarbeitet
                            continue

                    i += 1

        except requests.RequestException as e:
            self.log(f"❌ Fehler beim PDF-Download: {e}")
        except Exception as e:
            self.log(f"❌ Fehler beim PDF-Parsing: {e}")

        self.log(f"\n{'='*80}")
        self.log(f"✓ Gesamt gescrapt: {total_products} Produkte")
        self.log(f"{'='*80}\n")

    def _standardize_waste_type(self, raw_name):
        """Wandelt PDF-Abfallart in standardisierten Namen um."""
        name_lower = raw_name.lower().strip()

        # Spezifischere Patterns werden zuerst geprüft (Liste-Reihenfolge)
        for pattern, standard in self.waste_type_mapping:
            if pattern in name_lower:
                return standard

        return None

    def _should_skip(self, raw_name):
        """Prüft ob Kategorie übersprungen werden soll."""
        name_lower = raw_name.lower()
        return any(skip in name_lower for skip in self.skip_categories)

    def _parse_price(self, price_str):
        """Parst Preis-String zu deutschem Format."""
        if not price_str:
            return None

        price_str = str(price_str).strip()

        # Leere oder ungültige Werte
        if price_str in ['-', '–', '', 'None']:
            return None

        # Zahlen extrahieren (z.B. "1,011.50 €" oder "101.15 €")
        # Entferne alles außer Zahlen, Komma, Punkt
        clean = re.sub(r'[^\d.,]', '', price_str)

        if not clean:
            return None

        # Format erkennen und konvertieren
        # PDF verwendet: 1,011.50 (englisches Format mit Tausender-Komma)
        # Ziel: 1011,50 (deutsches Format)

        # Wenn Komma vor Punkt → englisches Format (1,011.50)
        if ',' in clean and '.' in clean:
            if clean.index(',') < clean.index('.'):
                # Englisch: 1,011.50 → 1011.50 → 1011,50
                clean = clean.replace(',', '')
                clean = clean.replace('.', ',')
            else:
                # Deutsch: 1.011,50 → 1011,50
                clean = clean.replace('.', '')
        elif '.' in clean:
            # Nur Punkt: könnte Dezimal sein (101.15) → 101,15
            # Prüfe ob nach dem Punkt genau 2 Ziffern
            parts = clean.split('.')
            if len(parts) == 2 and len(parts[1]) == 2:
                clean = clean.replace('.', ',')
            else:
                # Tausender-Punkt entfernen
                clean = clean.replace('.', '')

        return clean if clean else None
