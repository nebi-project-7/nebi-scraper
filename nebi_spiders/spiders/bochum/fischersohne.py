"""
FischerSöhne Spider
Extrahiert Preise für Container-Entsorgung in Bochum
Website: https://www.fischersoehne.de/preise/containerbereitstellung.htm

Hinweis: fischersoehne.de blockiert Verbindungen von Cloud-Providern (Azure/GitHub Actions)
auf TCP-Ebene. Daher wird Scrapy's Downloader umgangen und Selenium direkt genutzt.
"""

import re
import logging

import scrapy
from scrapy.http import HtmlResponse

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import TimeoutException, WebDriverException
from webdriver_manager.chrome import ChromeDriverManager
from time import sleep


class FischerSohneSpider(scrapy.Spider):
    name = "fischersohne"

    TARGET_URL = "https://www.fischersoehne.de/preise/containerbereitstellung.htm"

    # Mapping der Abfallarten (Website-Name → Standard-Name)
    WASTE_TYPE_MAPPING = {
        "Gartenabfälle": "Gartenabfälle",
        "Altholz, Kategorie AI-AIII": "Holz A1-A3",
        "Gemischte Materialien / Sperrmüll": "Sperrmüll",
        "Bauschutt, sauber (mineralisch)": "Bauschutt rein",
        "Bauschutt, unsauber": "Bauschutt unrein",
        "Baustoffe auf Gipsbasis": "Gips",
        "Bodenaushub / Erde + Steine": "Bodenaushub",
    }

    def __init__(self):
        logging.getLogger("selenium").setLevel(logging.WARNING)
        logging.getLogger("urllib3").setLevel(logging.WARNING)

        options = webdriver.ChromeOptions()
        options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.add_argument('--window-size=1920,1080')

        service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=options)
        self.driver.set_page_load_timeout(30)

    def closed(self, reason):
        try:
            self.driver.quit()
        except Exception:
            pass

    async def start(self):
        """Bypass Scrapy's Downloader — die Zielseite blockiert Cloud-IPs auf TCP-Ebene.
        Wir routen Scrapy durch example.com (immer erreichbar), damit parse() aufgerufen wird.
        Die eigentliche Seitenladung erfolgt in parse() über Selenium.

        Scrapy 2.13+: start_requests() wurde durch die async-Methode start() ersetzt.
        Da wir start() überschreiben, wird nie auf das nicht vorhandene start_urls zugegriffen."""
        yield scrapy.Request(
            url='https://example.com',
            callback=self.parse,
            dont_filter=True,
        )

    def parse(self, response):
        self.log(f"\n{'='*80}")
        self.log(f"Starte FischerSöhne Scraping für Bochum")
        self.log(f"URL: {self.TARGET_URL}")
        self.log(f"{'='*80}\n")

        total_products = 0

        try:
            self.driver.get(self.TARGET_URL)
            sleep(3)

            # Prüfe ob Seite geladen wurde
            page_title = self.driver.title
            self.log(f"Seite geladen: '{page_title}'")

            if not page_title or "error" in page_title.lower():
                self.log("WARNUNG: Seite konnte nicht korrekt geladen werden")
                return

            # Finde alle Tabellen
            tables = self.driver.find_elements(By.TAG_NAME, "table")
            self.log(f"Gefundene Tabellen: {len(tables)}")

            for table in tables:
                rows = table.find_elements(By.TAG_NAME, "tr")

                current_waste_type = None

                for row in rows:
                    cells = row.find_elements(By.TAG_NAME, "td")
                    if not cells:
                        # Prüfe Header
                        headers = row.find_elements(By.TAG_NAME, "th")
                        if headers:
                            header_text = headers[0].text.strip()
                            # Prüfe ob es eine Abfallart ist
                            for original, mapped in self.WASTE_TYPE_MAPPING.items():
                                if original in header_text:
                                    current_waste_type = mapped
                                    self.log(f"\n--- {current_waste_type} ---")
                                    break
                        continue

                    row_text = row.text.strip()

                    # Suche nach Zeilen mit Größe und Preis
                    # Format: "3,5 cbm Container 280,00 €" oder ähnlich
                    size_match = re.search(r'(\d+[,.]?\d*)\s*(?:cbm|m³)', row_text, re.IGNORECASE)
                    price_match = re.search(r'(\d+[,.]?\d*)\s*€', row_text)

                    if size_match and price_match and current_waste_type:
                        size_raw = size_match.group(1).replace(',', '.')
                        size = f"{size_raw} m³"
                        price = price_match.group(1).replace('.', ',')

                        # Prüfe ob es ein Container mit Deckel ist
                        has_deckel = "deckel" in row_text.lower()

                        # Bei 5 cbm ist Deckel inklusive, sonst 60 EUR
                        lid_price = "inklusive" if has_deckel else "60 EUR"

                        product = {
                            "source": "FischerSöhne",
                            "title": f"{size} {current_waste_type}",
                            "type": current_waste_type,
                            "city": "Bochum",
                            "size": size,
                            "price": price,
                            "lid_price": lid_price,
                            "arrival_price": "inklusive",
                            "departure_price": "inklusive",
                            "max_rental_period": "14 Tage",
                            "fee_after_max": "1,70 EUR/Tag",
                            "cancellation_fee": None,
                            "URL": self.TARGET_URL
                        }

                        total_products += 1
                        self.log(f"  ✓ {size}: {price} EUR")
                        yield product

        except TimeoutException:
            self.log("FEHLER: Selenium Timeout — Seite nicht erreichbar (30s)")
            self.log("Die Website blockiert möglicherweise Cloud-Provider-IPs.")
        except WebDriverException as e:
            self.log(f"FEHLER: WebDriver-Problem: {e}")
        except Exception as e:
            self.log(f"FEHLER: {e}")
            import traceback
            self.log(traceback.format_exc())

        self.log(f"\n{'='*80}")
        self.log(f"Gesamt gescrapt: {total_products} Produkte")
        self.log(f"{'='*80}\n")
