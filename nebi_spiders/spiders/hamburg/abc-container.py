"""
ABC Container Spider
Extrahiert Preise für Container-Entsorgung in Hamburg
Quelle: https://abccontainer.de/wp-content/uploads/2025-04-Preisliste-Container1.pdf
Stand: 01.04.2025
"""

from scrapy import Spider


class ABCContainerHamburgSpider(Spider):
    name = "abc-container-hamburg"
    allowed_domains = ["abccontainer.de"]
    start_urls = ["https://abccontainer.de/"]

    # Preise aus PDF-Preisliste (Brutto inkl. 19% MwSt)
    # Format: (waste_type, {size: price})
    # Container-Größen: 1m³, 6m³, 10m³, 14m³, 25m³, 30m³
    price_data = [
        ("Bauschutt", {
            "1": "101,15",
            "6": "499,80",
            "10": "833,00",
        }),
        ("Beton", {
            "1": "89,25",
            "6": "214,20",
            "10": "357,00",
        }),
        ("Boden", {
            "1": "119,00",
            "6": "535,50",
            "10": "892,50",
        }),
        ("Boden mit Steinen", {
            "1": "119,00",
            "6": "606,90",
            "10": "1011,50",
        }),
        ("Boden mit Wurzeln", {
            "1": "119,00",
            "6": "642,60",
            "10": "1071,00",
        }),
        ("Baumischabfall", {
            "1": "103,53",
            "6": "514,08",
            "10": "856,80",
            "14": "1199,52",
            "25": "2142,00",
            "30": "2570,40",
        }),
        ("Baumischabfall mit Bauschutt", {
            "1": "130,90",
            "6": "714,00",
            "10": "1190,00",
            "14": "1666,00",
            "25": "2975,00",
            "30": "3570,00",
        }),
        ("Baumischabfall nicht recycelbar", {
            "1": "166,60",
            "6": "892,50",
            "10": "1487,50",
            "14": "2082,50",
            "25": "3718,75",
            "30": "4462,50",
        }),
        ("Sperrmüll", {
            "1": "101,15",
            "6": "535,50",
            "10": "892,50",
            "14": "1249,50",
            "25": "2231,25",
            "30": "2677,50",
        }),
        ("Holz A1-A3", {
            "1": "89,25",
            "6": "271,32",
            "10": "452,20",
            "14": "633,08",
            "25": "1130,50",
            "30": "1356,60",
        }),
        ("Holz A4", {
            "1": "89,25",
            "6": "428,40",
            "10": "714,00",
            "14": "999,60",
            "25": "1785,00",
            "30": "2142,00",
        }),
        ("Gartenabfälle", {
            "1": "77,35",
            "6": "285,60",
            "10": "476,00",
            "14": "666,40",
            "25": "1190,00",
            "30": "1428,00",
        }),
        ("Gartenabfälle (Laub/Gras)", {
            "1": "77,35",
            "6": "307,02",
            "10": "511,70",
            "14": "716,38",
            "25": "1279,25",
            "30": "1535,10",
        }),
        ("Stammholz", {
            "6": "357,00",
            "10": "595,00",
            "14": "833,00",
            "25": "1487,50",
            "30": "1785,00",
        }),
        ("Dachpappe", {
            "1": "285,60",
            "6": "1677,90",
            "10": "2796,50",
        }),
    ]

    def parse(self, response):
        self.log(f"\n{'='*80}")
        self.log(f"Starte ABC Container Scraping (Preisliste Stand 01.04.2025)")
        self.log(f"{'='*80}\n")

        total_products = 0
        pdf_url = "https://abccontainer.de/wp-content/uploads/2025-04-Preisliste-Container1.pdf"

        for waste_type, prices in self.price_data:
            self.log(f"\n--- Verarbeite: {waste_type} ---")

            for size, price in prices.items():
                total_products += 1
                self.log(f"  ✓ {size}m³: {price}€")

                yield {
                    "source": "ABC Container",
                    "title": f"{waste_type} {size} m³",
                    "type": waste_type,
                    "city": "Hamburg",
                    "size": size,
                    "price": price,
                    "lid_price": None,
                    "arrival_price": "inklusive",
                    "departure_price": "inklusive",
                    "max_rental_period": None,
                    "fee_after_max": None,
                    "cancellation_fee": "101,15",  # 85€ netto = 101,15€ brutto
                    "URL": pdf_url
                }

        self.log(f"\n{'='*80}")
        self.log(f"✓ Gesamt gescrapt: {total_products} Produkte")
        self.log(f"{'='*80}\n")
