import logging
import re
from time import sleep

from scrapy import Spider
from scrapy.selector import Selector

from selenium import webdriver
from selenium.webdriver.common.by import By


class OresContainerProductsSpider(Spider):
    name = "ores-container-products"
    allowed_domains = ["containerentsorgung-berlin.de"]

    # Waste type URLs
    waste_type_urls = [
        ("https://containerentsorgung-berlin.de/Bauschutt-mineral.-oh.-Gipsanteile/", "Bauschutt mineral. oh. Gipsanteile"),
        ("https://containerentsorgung-berlin.de/Holz-Entsorgung/Holz-unbehandelt/", "Holz unbehandelt"),
        ("https://containerentsorgung-berlin.de/Holz-Entsorgung/Holz-behandelt/", "Holz behandelt"),
        ("https://containerentsorgung-berlin.de/Gewerbeabfaelle/", "Gewerbeabfälle"),
        ("https://containerentsorgung-berlin.de/Sperrmuell/", "Sperrmüll"),
        ("https://containerentsorgung-berlin.de/Boden/", "Boden"),
        ("https://containerentsorgung-berlin.de/Bau-und-Abbruchabfaelle/", "Bau- und Abbruchabfälle"),
        ("https://containerentsorgung-berlin.de/Gruenabfall-Laub-Grasschnitt/", "Grünabfall Laub Grasschnitt"),
        ("https://containerentsorgung-berlin.de/Strauchwerk/Strauchwerk-mit-Stammholz/", "Strauchwerk mit Stammholz"),
        ("https://containerentsorgung-berlin.de/Strauchwerk/Strauchwerk-ohne-Stammholz/", "Strauchwerk ohne Stammholz"),
    ]

    start_urls = ["https://containerentsorgung-berlin.de/"]

    def __init__(self):
        logging.getLogger("selenium").setLevel(logging.WARNING)
        logging.getLogger("urllib3").setLevel(logging.WARNING)

        self.driver = webdriver.Chrome()
        self.driver.maximize_window()

        # Rental period will be extracted from AGB
        self.max_rental_period = None

    def closed(self, reason):
        try:
            self.driver.quit()
        except Exception:
            pass

    def parse(self, response):
        self.log(f"\n{'='*80}")
        self.log(f"Starte ORES Containerlogistik Scraping")
        self.log(f"{'='*80}\n")

        # Extract rental period from AGB page
        self._extract_rental_period_from_agb()

        total_products = 0

        # For each waste type
        for url, display_name in self.waste_type_urls:
            self.log(f"\n--- Verarbeite: {display_name} ---")

            try:
                # Navigate to waste type page
                self.driver.get(url)
                sleep(3)

                # Dismiss cookie banner (only on first call)
                self._dismiss_cookie_banner()

                # Find all product links on the page
                product_links = self._find_product_links()

                if not product_links:
                    self.log(f"  ⚠️ Keine Produkt-Links gefunden")
                    continue

                self.log(f"  Gefunden: {len(product_links)} Produkte")

                # For each product link, visit detail page and extract data
                for product_url in product_links:
                    try:
                        # Navigate to product detail page
                        self.driver.get(product_url)
                        sleep(2)

                        # Extract product details
                        product = self._extract_product(product_url, display_name)

                        if product:
                            total_products += 1
                            self.log(f"  ✓ {product['size']}m³: {product['price']}€ (Deckel: {product['lid_price']}€)")
                            yield product

                    except Exception as e:
                        self.log(f"  ❌ Fehler bei {product_url}: {e}")
                        continue

            except Exception as e:
                self.log(f"  ❌ Fehler: {e}")
                continue

        self.log(f"\n{'='*80}")
        self.log(f"✓ Gesamt gescrapt: {total_products} Produkte")
        self.log(f"{'='*80}\n")

    def _extract_rental_period_from_agb(self):
        """
        Extrahiert die maximale Mietdauer aus der AGB-Seite.
        """
        try:
            agb_url = "https://containerentsorgung-berlin.de/Informationen/Unsere-AGB/"
            self.log(f"Extrahiere Mietdauer aus AGB: {agb_url}")

            self.driver.get(agb_url)
            sleep(2)

            # Get visible text
            visible_text = self.driver.execute_script("return document.body.innerText;")

            # Search for pattern: "max. X Kalendertagen" in § 2
            # Pattern: "max. 6 Kalendertagen" or similar
            rental_match = re.search(r'max\.\s*(\d+)\s*Kalendertag', visible_text, re.IGNORECASE)
            if rental_match:
                self.max_rental_period = rental_match.group(1)
                self.log(f"✓ Mietdauer extrahiert: {self.max_rental_period} Tage")
            else:
                # Fallback to default
                self.max_rental_period = "6"
                self.log(f"⚠️ Mietdauer nicht gefunden, nutze Standard: {self.max_rental_period} Tage")

        except Exception as e:
            self.log(f"⚠️ Fehler beim Extrahieren der Mietdauer: {e}")
            self.max_rental_period = "6"  # Fallback

    def _dismiss_cookie_banner(self):
        """
        Versucht, den Cookie-Banner zu schließen.
        """
        try:
            cookie_buttons = self.driver.find_elements(
                By.XPATH,
                "//button[contains(., 'Akzeptieren') or contains(., 'Accept') or contains(., 'OK') or contains(@class, 'cookie')]"
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

    def _find_product_links(self):
        """
        Findet alle Produkt-Links auf der aktuellen Seite.
        """
        product_links = []

        try:
            # Find all product links with class "product-name"
            links = self.driver.find_elements(By.CSS_SELECTOR, "a.product-name")

            for link in links:
                href = link.get_attribute("href")
                if href and href not in product_links:
                    product_links.append(href)

        except Exception as e:
            self.log(f"Fehler beim Finden der Produkt-Links: {e}")

        return product_links

    def _extract_product(self, product_url: str, waste_type: str):
        """
        Extrahiert Produktdetails von der Produktseite.
        """
        try:
            # Extract size from page title
            page_title = self.driver.title
            size = ""

            # Pattern: X,X m³ or X m³
            size_match = re.search(r'(\d+(?:[.,]\d+)?)\s*m³', page_title)
            if size_match:
                size = size_match.group(1).replace(',', '.')

            # Extract base price from visible text
            # The page shows: 0,00€ (cart), then 342,99€ or 1.368,99€ (product price), then 15,00€ (lid), etc.
            price = ""
            visible_text = self.driver.execute_script("return document.body.innerText;")

            # Find all prices in the visible text (including thousand separators)
            # Pattern matches: 1.368,99 or 368,99 or 0,00
            price_matches = re.findall(r'([\d.,]+)\s*€', visible_text)
            if len(price_matches) >= 2:
                # Skip first price (0,00 cart total), take second price (product price)
                # But only if first is 0,00
                if price_matches[0] == "0,00":
                    # Remove thousand separator (.) and replace decimal separator (,) with (.)
                    price = price_matches[1].replace('.', '').replace(',', '.')
                else:
                    # If first is not 0,00, it might be the correct price
                    price = price_matches[0].replace('.', '').replace(',', '.')
            elif len(price_matches) >= 1:
                price = price_matches[0].replace('.', '').replace(',', '.')

            # Extract lid price (Deckel)
            # Find "Mit Deckel" text on the page, then find associated price
            lid_price = ""
            try:
                visible_text = self.driver.execute_script("return document.body.innerText;")
                deckel_pos = visible_text.find("Mit Deckel")
                if deckel_pos != -1:
                    # Search for price after "Mit Deckel" position
                    remaining_text = visible_text[deckel_pos:]
                    lid_match = re.search(r'([\d.,]+)\s*€', remaining_text)
                    if lid_match:
                        # Remove thousand separator (.) and replace decimal separator (,) with (.)
                        lid_price = lid_match.group(1).replace('.', '').replace(',', '.')
            except:
                pass

            if not size or not price:
                self.log(f"⚠️ Größe oder Preis nicht gefunden für {product_url}")
                return None

            product = {
                "source": "ORES Containerlogistik",
                "type": waste_type,
                "city": "Berlin",
                "size": size,
                "price": price,
                "lid_price": lid_price,
                "arrival_price": "Abhängig von Zone 4, 6, 10, 12 EURO",
                "departure_price": "inklusive",
                "max_rental_period": self.max_rental_period or "6",
                "fee_after_max": "",
                "cancellation_fee": "109.48",
                "URL": product_url
            }

            return product

        except Exception as e:
            self.log(f"Fehler beim Extrahieren: {e}")
            return None
