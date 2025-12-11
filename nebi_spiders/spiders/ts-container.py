import logging
import re
from time import sleep

from scrapy import Spider
from scrapy.selector import Selector

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException


class TSContainerProductsSpider(Spider):
    name = "ts-container-products"
    allowed_domains = ["ts-container.de"]

    # Produktkategorien URLs
    start_urls = [
        "https://ts-container.de/baumischabfaelle/",
        "https://ts-container.de/bauschutt-3/",
        "https://ts-container.de/holzabfall-2/",
        "https://ts-container.de/sperrmuell/",
        "https://ts-container.de/gartenabfaelle/",
    ]

    def __init__(self):
        logging.getLogger("selenium").setLevel(logging.WARNING)
        logging.getLogger("urllib3").setLevel(logging.WARNING)

        options = webdriver.ChromeOptions()
        options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.add_argument('--window-size=1920,1080')
        self.driver = webdriver.Chrome(options=options)

        # Dynamische Werte aus AGB holen (falls vorhanden)
        self.agb_values = self._fetch_agb_values()

    def closed(self, reason):
        try:
            self.driver.quit()
        except Exception:
            pass

    # ---------------------------------------------------------
    # AGB-Werte dynamisch von der Website holen
    # ---------------------------------------------------------
    def _fetch_agb_values(self):
        """
        Holt dynamische Werte von der AGB-Seite (falls vorhanden).
        """
        self.log("Suche nach AGB-Seite für ts-container.de...")

        try:
            # Versuche AGB-Seite zu finden
            self.driver.get("https://ts-container.de/agb/")
            sleep(2)

            sel = Selector(text=self.driver.page_source)
            agb_text = " ".join(sel.xpath('//text()').getall())

            # Extrahiere Mietzeit (falls vorhanden)
            rental_match = re.search(r'Mietzeit von (\d+) Tagen', agb_text)
            max_rental_period = rental_match.group(1) if rental_match else "14"

            self.log(f"✓ AGB-Werte geladen: Mietzeit={max_rental_period} Tage")

            return {
                "max_rental_period": max_rental_period,
                "fee_after_max": "siehe AGB",
                "cancellation_fee": "siehe AGB",
            }

        except Exception as e:
            self.log(f"⚠️ Keine AGB gefunden oder Fehler: {e}. Verwende Standardwerte.")
            return {
                "max_rental_period": "14",
                "fee_after_max": "siehe AGB",
                "cancellation_fee": "siehe AGB",
            }

    # ---------------------------------------------------------
    # Jede Kategorieseite scrapen
    # ---------------------------------------------------------
    def parse(self, response):
        url = response.url
        self.log(f"\n{'='*80}")
        self.log(f"Starte Kategorieseite: {url}")
        self.log(f"{'='*80}\n")

        # Seite mit Selenium öffnen
        self.driver.get(url)
        sleep(3)

        # Cookie-Banner wegklicken (falls vorhanden)
        try:
            cookie_button = WebDriverWait(self.driver, 5).until(
                EC.element_to_be_clickable(
                    (By.XPATH, '//button[contains(., "Akzeptieren") or contains(., "OK")]')
                )
            )
            cookie_button.click()
            self.log("Cookie-Banner akzeptiert.")
            sleep(1)
        except Exception:
            self.log("Cookie-Banner nicht gefunden oder bereits akzeptiert.")

        # HTML holen
        sel = Selector(text=self.driver.page_source)

        # Abfallart aus URL ableiten
        waste_type = self._extract_waste_type_from_url(url)

        # Produkte finden
        products = sel.css('.woocommerce-loop-product__title')
        self.log(f"Gefunden: {len(products)} Produkte für {waste_type}")

        # Für jedes Produkt
        for idx in range(len(products)):
            # HTML neu holen für jedes Produkt
            sel = Selector(text=self.driver.page_source)

            # Titel
            titles = sel.css('.woocommerce-loop-product__title::text').getall()
            if idx >= len(titles):
                continue

            title = titles[idx].strip()

            # Größe aus Titel extrahieren (z.B. "3,5m³" → "3.5")
            size_match = re.search(r'(\d+[.,]?\d*)\s*m³', title)
            size = size_match.group(1).replace(',', '.') if size_match else ""

            # Preis extrahieren
            prices = sel.css('.price')
            if idx >= len(prices):
                price = "Preis auf Anfrage"
            else:
                price_text = prices[idx].css('::text').getall()
                price_clean = ''.join(price_text).strip()
                # Format: "461,06 €" → "461,06"
                price_match = re.search(r'(\d{1,3}(?:[.,]\d{3})*[.,]\d{2})', price_clean)
                price = price_match.group(1) if price_match else price_clean

            # Produkt-Link (optional)
            links = sel.css('a.woocommerce-LoopProduct-link::attr(href), .product a::attr(href)').getall()
            product_url = links[idx] if idx < len(links) else url

            # Item bauen
            item = self._build_item(title, waste_type, size, price, product_url)
            self.log(f"✓ ITEM: type={waste_type}, size={size}m³, price={price}€")
            yield item

        self.log(f"\nKategorieseite abgeschlossen: {waste_type} ({len(products)} Produkte)\n")

    # ---------------------------------------------------------
    # Hilfsfunktion: Abfallart aus URL extrahieren
    # ---------------------------------------------------------
    def _extract_waste_type_from_url(self, url: str) -> str:
        """
        Extrahiert Abfallart aus URL.
        z.B. "https://ts-container.de/baumischabfaelle/" → "Baumischabfall"
        """
        mapping = {
            "baumischabfaelle": "Baumischabfall",
            "bauschutt": "Bauschutt",
            "holzabfall": "Holzabfall",
            "sperrmuell": "Sperrmüll",
            "gartenabfaelle": "Gartenabfall",
        }

        for key, value in mapping.items():
            if key in url.lower():
                return value

        return "Unbekannt"

    # ---------------------------------------------------------
    # Hilfsfunktion: Item bauen
    # ---------------------------------------------------------
    def _build_item(
        self,
        title: str,
        waste_type: str,
        size: str,
        price: str,
        product_url: str,
    ) -> dict:
        return {
            "source": "ts-container.de",
            "title": title,
            "type": waste_type,
            "city": "Berlin",
            "size": size,
            "price": price,
            "lid_price": "kostenlos wenn verfügbar",
            "arrival_price": "inklusive",
            "departure_price": "inklusive",
            "max_rental_period": self.agb_values["max_rental_period"],
            "fee_after_max": self.agb_values["fee_after_max"],
            "cancellation_fee": self.agb_values["cancellation_fee"],
            "URL": product_url,
        }
