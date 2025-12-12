import logging
from scrapy import Spider


class AserContainerProductsSpider(Spider):
    name = "aser-container-products"
    allowed_domains = ["aser-berlin.de"]

    # PDF URL
    pdf_url = "http://www.aser-berlin.de/preisliste.pdf"

    start_urls = ["http://www.aser-berlin.de/"]

    def __init__(self):
        # Preisdaten aus der Preisliste (gültig ab 01/2024)
        # Format: (Abfallart, Selbstanlieferung, Container 3m³, Container 5,5-10m³, Einheit)
        self.price_data = [
            ("Baumischabfall", "79.00", "70.50", "70.50", "m³"),
            ("Gewerbeabfälle", "79.00", "70.50", "70.50", "m³"),
            ("Dämmstoffe Mineralwolle, KMF, Fermacell", "66.00", "56.00", "56.00", "m³"),
            ("Gipsabfälle (Rigips, Yton, Poroton)", "62.00", "57.00", "57.00", "m³"),
            ("Bauschutt recycelfähig", "55.00", "49.00", "49.00", "t/m³"),
            ("Bauschutt nicht recycelfähig", "65.00", "60.00", "60.00", "t/m³"),
            ("Holz A1-A3", "42.00", "38.00", "38.00", "m³"),
            ("Holz A4", "49.00", "49.00", "49.00", "m³"),
            ("Sperrmüll (verwertbar 40-50%)", "69.00", "59.00", "59.00", "m³"),
            ("Sperrmüll (verwertbar <40%)", "79.00", "69.00", "69.00", "m³"),
            ("Asbestzement", "220.00", "220.00", "220.00", "m³"),
            ("Gartenabfälle", "25.50", "25.50", "25.50", "m³"),
        ]

        # Service-Leistungen
        self.transport_absetzcontainer = "96.00"
        self.transport_abrollcontainer = "145.00"
        self.mindermenge_pauschale = "35.00"

        # MwSt. und Stornierung
        self.mwst_rate = 1.19  # 19% MwSt.
        self.cancellation_fee = "180€ bis 1,5 Std. oder 130€ pro Std. über 1,5 Std."

    def parse(self, response):
        self.log(f"\n{'='*80}")
        self.log(f"Starte Aser Containerdienst Scraping")
        self.log(f"{'='*80}\n")

        total_products = 0

        # Für jede Abfallart Produkte erstellen (nur Container, keine Selbstanlieferung)
        for waste_type, self_delivery, container_3m3, container_large, unit in self.price_data:
            # Produkt für Container 3m³
            if container_3m3 and container_3m3 != "Kostenlos" and container_3m3 != "Auf Anfrage":
                try:
                    price_3m3 = float(container_3m3)
                    total_price_3m3 = price_3m3 * 3 * self.mwst_rate  # 3m³ + 19% MwSt.

                    product_3m3 = {
                        "source": "Aser Containerdienst",
                        "title": f"3 m³ {waste_type}",
                        "type": waste_type,
                        "city": "Berlin",
                        "size": "3",
                        "price": f"{total_price_3m3:.2f}".replace('.', ','),
                        "lid_price": "",
                        "arrival_price": self.transport_absetzcontainer,
                        "departure_price": "inklusive",
                        "max_rental_period": "",
                        "fee_after_max": "",
                        "cancellation_fee": self.cancellation_fee,
                        "URL": self.pdf_url
                    }
                    total_products += 1
                    self.log(f"  ✓ {waste_type[:40]:40} | 3m³ | {container_3m3}€/{unit} → {total_price_3m3:.2f}€ (inkl. 19% MwSt.)")
                    yield product_3m3
                except ValueError:
                    pass

            # Produkte für Container 5,5m³, 7m³, 10m³
            if container_large and container_large != "Kostenlos" and container_large != "Auf Anfrage":
                for size in ["5.5", "7", "10"]:
                    try:
                        price_per_m3 = float(container_large)
                        size_float = float(size)
                        total_price = price_per_m3 * size_float * self.mwst_rate  # + 19% MwSt.

                        # Wähle Transport basierend auf Größe
                        transport = self.transport_abrollcontainer if size_float >= 10 else self.transport_absetzcontainer

                        product_large = {
                            "source": "Aser Containerdienst",
                            "title": f"{size} m³ {waste_type}",
                            "type": waste_type,
                            "city": "Berlin",
                            "size": size,
                            "price": f"{total_price:.2f}".replace('.', ','),
                            "lid_price": "",
                            "arrival_price": transport,
                            "departure_price": "inklusive",
                            "max_rental_period": "",
                            "fee_after_max": "",
                            "cancellation_fee": self.cancellation_fee,
                            "URL": self.pdf_url
                        }
                        total_products += 1
                        self.log(f"  ✓ {waste_type[:40]:40} | {size}m³ | {container_large}€/{unit} → {total_price:.2f}€ (inkl. 19% MwSt.)")
                        yield product_large
                    except ValueError:
                        pass

        self.log(f"\n{'='*80}")
        self.log(f"✓ Gesamt gescrapt: {total_products} Produkte")
        self.log(f"{'='*80}\n")
