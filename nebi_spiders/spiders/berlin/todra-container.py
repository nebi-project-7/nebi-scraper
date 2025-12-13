import logging
import re
import tempfile
import os
from urllib.request import urlretrieve

from scrapy import Spider
import pdfplumber


class TodraContainerProductsSpider(Spider):
    name = "todra-container-products"
    allowed_domains = ["todra-dienstleistungen.de"]

    # PDF URL
    pdf_url = "https://www.todra-dienstleistungen.de/wp-content/uploads/2025/10/A4-Preisliste-mit-AGB.pdf"

    start_urls = ["https://www.todra-dienstleistungen.de/"]

    def __init__(self):
        # AGB-Daten (werden aus PDF extrahiert)
        self.max_rental_period = "10"
        self.fee_after_max = "3€"
        self.cancellation_fee = "75"

        # Container-Größen und ihre Spaltenindizes
        self.container_sizes = [
            ("5.5", 4),   # 5,5 m³ ist Spalte 4
            ("7.5", 5),   # 7,5 m³ ist Spalte 5
            ("10", 6),    # 10 m³ ist Spalte 6
        ]

        # Abfallarten-Mapping für konsistente Benennung
        self.waste_type_mapping = {
            'unbehandeltes Holz (A1-A3)': 'Holz A1-A3',
            'behandeltes Holz (A4)': 'Holz A4',
            'reiner Bauschutt': 'Bauschutt (rein)',
            'unreiner Bauschutt': 'Bauschutt (unrein)',
            'Boden unrein': 'Boden (unrein)',
            'Boden rein': 'Boden (rein)',
            'Mineralfaserdämmstoffe KMF': 'Dämmstoffe',
            'Gibskarton und Porenbeton': 'Gipskarton und Porenbeton',
        }

    def parse(self, response):
        self.log(f"\n{'='*80}")
        self.log(f"Starte TODRA Dienstleistungen PDF Scraping")
        self.log(f"{'='*80}\n")

        # Lade PDF herunter
        temp_pdf = self._download_pdf()

        if not temp_pdf:
            self.log("❌ PDF konnte nicht heruntergeladen werden")
            return

        try:
            # Extrahiere AGB-Daten
            self._extract_agb_data(temp_pdf)

            # Extrahiere Produkte aus PDF
            total_products = 0

            for product in self._extract_products(temp_pdf):
                total_products += 1
                self.log(f"  ✓ {product['type'][:40]:40} | {product['size']}m³ | {product['price']}€")
                yield product

            self.log(f"\n{'='*80}")
            self.log(f"✓ Gesamt gescrapt: {total_products} Produkte")
            self.log(f"{'='*80}\n")

        finally:
            # Lösche temporäre PDF-Datei
            if os.path.exists(temp_pdf):
                os.remove(temp_pdf)
                self.log(f"✓ Temporäre PDF gelöscht: {temp_pdf}")

    def _download_pdf(self):
        """
        Lädt das PDF herunter und gibt den Pfad zur temporären Datei zurück
        """
        try:
            self.log(f"Lade PDF herunter: {self.pdf_url}")

            # Erstelle temporäre Datei
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.pdf')
            temp_path = temp_file.name
            temp_file.close()

            # Lade PDF herunter
            urlretrieve(self.pdf_url, temp_path)

            self.log(f"✓ PDF heruntergeladen: {temp_path}")
            return temp_path

        except Exception as e:
            self.log(f"❌ Fehler beim Herunterladen des PDFs: {e}")
            return None

    def _extract_agb_data(self, pdf_path):
        """
        Extrahiert AGB-Daten aus Seite 2 des PDFs
        """
        try:
            with pdfplumber.open(pdf_path) as pdf:
                if len(pdf.pages) < 2:
                    self.log("⚠️ PDF hat keine zweite Seite (AGB)")
                    return

                self.log("Extrahiere AGB-Informationen von Seite 2...")
                agb_page = pdf.pages[1]
                agb_text = agb_page.extract_text()

                if agb_text:
                    # Suche nach Mietdauer: "beträgt diese 10 Werktage"
                    rental_match = re.search(r'beträgt diese\s+(\d+)\s+Werktage', agb_text)
                    if rental_match:
                        self.max_rental_period = rental_match.group(1)
                        self.log(f"  ✓ Mietdauer: {self.max_rental_period} Werktage")

                    # Suche nach Gebühr: "3,00 Euro / Tag" - behalte Komma
                    fee_match = re.search(r'(\d+[.,]\d+)\s*Euro\s*/\s*Tag', agb_text)
                    if fee_match:
                        self.fee_after_max = fee_match.group(1) + '€'
                        self.log(f"  ✓ Gebühr nach Mietdauer: {self.fee_after_max}/Tag")

                    # Suche nach Stornierungsgebühr: "75 € für die Leerfahrt"
                    cancel_match = re.search(r'(\d+)\s*€\s+für die Leerfahrt', agb_text)
                    if cancel_match:
                        self.cancellation_fee = cancel_match.group(1)
                        self.log(f"  ✓ Stornierungsgebühr (Leerfahrt): {self.cancellation_fee}€")

        except Exception as e:
            self.log(f"⚠️ Fehler beim Extrahieren der AGB-Daten: {e}")

    def _extract_products(self, pdf_path):
        """
        Extrahiert Produkte aus der Preistabelle auf Seite 1
        """
        try:
            with pdfplumber.open(pdf_path) as pdf:
                page = pdf.pages[0]  # Preisliste ist auf Seite 1

                # Extrahiere die Tabelle
                tables = page.extract_tables()

                if not tables:
                    self.log("❌ Keine Tabelle im PDF gefunden!")
                    return

                table = tables[0]

                # Überspringe Header-Zeilen (erste 2 Zeilen)
                data_rows = table[2:]

                current_category = ""

                for row in data_rows:
                    # row[0] = Position, row[1] = Hauptrubrik, row[2] = Unterrubrik,
                    # row[3] = Beschreibung, row[4-6] = Preise

                    # Aktualisiere Kategorie wenn neue Hauptrubrik
                    if row[1] and row[1].strip():
                        current_category = row[1].strip()

                    # Beschreibung aus Spalte 3 oder Hauptrubrik
                    if row[3] and row[3] != "/" and row[3].strip():
                        waste_type = row[3].strip().replace('\n', ' ')
                    elif current_category:
                        waste_type = current_category.replace('\n', ' ')
                    else:
                        continue

                    # Wende Mapping für konsistente Benennung an
                    waste_type = self.waste_type_mapping.get(waste_type, waste_type)

                    # Für jede Container-Größe ein Produkt erstellen
                    for size, col_idx in self.container_sizes:
                        price_per_m3 = row[col_idx]

                        # Überspringe wenn Preis "/" oder leer ist
                        if not price_per_m3 or price_per_m3 == "/" or not price_per_m3.strip():
                            continue

                        try:
                            # Berechne Gesamtpreis: €/m³ × Containergröße
                            price_per_m3_float = float(price_per_m3.replace(',', '.'))
                            size_float = float(size)
                            total_price = price_per_m3_float * size_float

                            product = {
                                "source": "TODRA Dienstleistungen",
                                "title": f"{size} m³ {waste_type}",
                                "type": waste_type,
                                "city": "Berlin",
                                "size": size,
                                "price": f"{total_price:.2f}".replace('.', ','),
                                "lid_price": "",
                                "arrival_price": "inklusive",
                                "departure_price": "inklusive",
                                "max_rental_period": self.max_rental_period,
                                "fee_after_max": self.fee_after_max,
                                "cancellation_fee": self.cancellation_fee,
                                "URL": self.pdf_url
                            }

                            yield product

                        except (ValueError, TypeError) as e:
                            self.log(f"⚠️ Fehler bei Verarbeitung: {waste_type} - {e}")
                            continue

        except Exception as e:
            self.log(f"❌ Fehler beim Extrahieren der Produkte: {e}")
