import logging
import re
from time import sleep

from scrapy import Spider
from scrapy.selector import Selector

from selenium import webdriver
from selenium.webdriver.common.by import By


class SchuttgeierProductsSpider(Spider):
    name = "schuttgeier-products"
    allowed_domains = ["schuttgeier.de"]
    start_urls = ["https://www.schuttgeier.de/angebot"]

    # Waste types we want to extract
    waste_types = [
        ("Bau-undAbbruchholz", "Bau- und Abbruchholz"),
        ("Baumischabfall", "Baumischabfall"),
        ("Bauschutt", "Bauschutt"),
        ("Beton", "Beton"),
        ("KompostierbareAbfälle", "Kompostierbare Abfälle"),
        ("Sperrmüll", "Sperrmüll"),
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

    def closed(self, reason):
        try:
            self.driver.quit()
        except Exception:
            pass

    def parse(self, response):
        self.log(f"\n{'='*80}")
        self.log(f"Starte Schuttgeier Scraping")
        self.log(f"{'='*80}\n")

        total_products = 0

        try:
            # Navigate to the page
            self.driver.get(response.url)
            sleep(3)

            # Try to dismiss cookie banner
            self._dismiss_cookie_banner()

            # Get the page source
            page_source = self.driver.page_source

            # Parse with Scrapy Selector
            selector = Selector(text=page_source)

            # Extract products for each waste type
            for class_name, display_name in self.waste_types:
                self.log(f"\n--- Verarbeite: {display_name} ---")

                # Find the div with class "mix {class_name}"
                waste_divs = selector.xpath(f'//div[contains(@class, "mix") and contains(@class, "{class_name}")]')

                if not waste_divs:
                    self.log(f"  ⚠️ Keine Daten gefunden für {display_name}")
                    continue

                # Get the first matching div
                waste_div = waste_divs[0]

                # Find all container items within this waste type section
                container_items = waste_div.xpath('.//div[@class="playlist-item"]')

                if not container_items:
                    self.log(f"  ⚠️ Keine Container-Items gefunden")
                    continue

                self.log(f"  Gefunden: {len(container_items)} Container-Größen")

                # Extract size and price from each container item
                for item in container_items:
                    # Each item has two <p> tags: first with size, second with price
                    p_tags = item.xpath('.//p')

                    if len(p_tags) < 2:
                        self.log(f"  ⚠️ Nicht genug <p> Tags gefunden: {len(p_tags)}")
                        continue

                    # First <p> contains size (e.g., "3\n㎡")
                    size_text = ''.join(p_tags[0].xpath('.//text()').getall())

                    # Extract digits from the text using regex
                    size_match = re.search(r'(\d+)', size_text)
                    size = size_match.group(1) if size_match else None

                    # Second <p> contains price (e.g., "185,00\n€")
                    price_text = ''.join(p_tags[1].xpath('.//text()').getall())

                    # Extract price using regex (format: XXX,XX)
                    price_match = re.search(r'(\d+,\d+)', price_text)
                    price = price_match.group(1).replace(',', '.') if price_match else None

                    if not size or not price:
                        self.log(f"  ⚠️ Größe oder Preis nicht vollständig extrahiert: size={size}, price={price}")
                        continue

                    product = {
                        "source": "schuttgeier.de",
                        "type": display_name,
                        "city": "Berlin",
                        "size": size,
                        "price": price,
                        "lid_price": "",
                        "arrival_price": "inklusive",
                        "departure_price": "inklusive",
                        "max_rental_period": "",
                        "fee_after_max": "",
                        "cancellation_fee": "",
                        "URL": response.url
                    }

                    total_products += 1
                    self.log(f"  ✓ {size}m³: {price}€")
                    yield product

        except Exception as e:
            self.log(f"❌ Fehler: {e}")
            import traceback
            self.log(traceback.format_exc())

        self.log(f"\n{'='*80}")
        self.log(f"✓ Gesamt gescrapt: {total_products} Produkte")
        self.log(f"{'='*80}\n")

    def _dismiss_cookie_banner(self):
        """
        Versucht, den Cookie-Banner zu schließen.
        """
        try:
            # Suche nach Cookie-Banner-Buttons
            cookie_buttons = self.driver.find_elements(
                By.XPATH,
                "//button[contains(., 'Akzeptieren') or contains(., 'Accept') or contains(., 'OK') or contains(@class, 'cookie') or contains(@id, 'cookie')]"
            )

            if cookie_buttons:
                for btn in cookie_buttons:
                    try:
                        if btn.is_displayed():
                            btn.click()
                            self.log("✓ Cookie-Banner geschlossen")
                            sleep(1)
                            return
                    except:
                        pass
        except:
            pass
