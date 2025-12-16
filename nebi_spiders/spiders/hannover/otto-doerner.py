"""
OTTO DÖRNER Spider
Extrahiert Preise für Container-Entsorgung in Hannover
Shop: https://www.doerner-shop.de/containerarten/
"""

import logging
import re
from time import sleep

from scrapy import Spider

from selenium import webdriver
from selenium.webdriver.common.by import By


class OttoDoernerSpider(Spider):
    name = "otto-doerner"
    allowed_domains = ["doerner-shop.de"]
    start_urls = ["https://www.doerner-shop.de/containerarten/"]

    # Abfallarten (URL-Slug -> Standardisierter Name)
    # Ignoriere: BigBags, Säcke, Aktenvernichtung, Miettoiletten
    waste_categories = [
        ("bauschutt", "Bauschutt"),
        ("baumischabfall", "Baumischabfall"),
        ("gartenabfall", "Gartenabfälle"),
        ("sperrmuell", "Sperrmüll"),
        ("boden", "Boden"),
        ("holz-behandelt", "Holz behandelt"),
        ("gips", "Gips"),
        ("beton", "Beton"),
        ("dachpappe", "Dachpappe"),
        ("porenbeton-ytong", "Porenbeton"),
    ]

    # Verfügbare Größen (URL-Suffix)
    sizes = ["03", "05", "07"]

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

        self.seen_products = set()
        self.cookies_accepted = False

    def closed(self, reason):
        try:
            self.driver.quit()
        except Exception:
            pass

    def parse(self, response):
        self.log(f"\n{'='*80}")
        self.log(f"Starte OTTO DÖRNER Scraping (Hannover)")
        self.log(f"{'='*80}\n")

        total_products = 0

        # Für jede Abfallart
        for url_slug, waste_type in self.waste_categories:
            self.log(f"\n--- Verarbeite: {waste_type} ---")

            try:
                # Gehe zur Übersichtsseite und finde Absetzcontainer-Link
                url = f"https://www.doerner-shop.de/container-bestellen/{url_slug}/hannover/"
                self.driver.get(url)
                sleep(2)

                # Cookie-Banner akzeptieren (nur einmal)
                if not self.cookies_accepted:
                    self._accept_cookies()
                    self.cookies_accepted = True

                # Finde Absetzcontainer-Link und extrahiere Produkt-ID
                product_id = self._find_product_id(url_slug)

                if not product_id:
                    self.log(f"  ⚠️ Kein Absetzcontainer gefunden für {waste_type}")
                    continue

                # Für jede Größe
                for size_code in self.sizes:
                    try:
                        # Konstruiere direkte URL für diese Größe
                        size_url = f"https://www.doerner-shop.de/absetzcontainer-fuer-{url_slug}-in-hannover/cs-h-{product_id}-m{size_code}"
                        self.driver.get(size_url)
                        sleep(2)

                        # Prüfe ob Seite existiert (404 oder Weiterleitung)
                        if "404" in self.driver.title.lower() or "nicht gefunden" in self.driver.page_source.lower():
                            continue

                        # Extrahiere Preis
                        price = self._get_current_price()
                        if not price:
                            continue

                        size = str(int(size_code))  # "03" -> "3"

                        product_key = f"{waste_type}|{size}"
                        if product_key not in self.seen_products:
                            self.seen_products.add(product_key)
                            total_products += 1

                            product = {
                                "source": "OTTO DÖRNER",
                                "title": f"{waste_type} {size} m³",
                                "type": waste_type,
                                "city": "Hannover",
                                "size": size,
                                "price": price,
                                "lid_price": None,
                                "arrival_price": "inklusive",
                                "departure_price": "inklusive",
                                "max_rental_period": None,
                                "fee_after_max": None,
                                "cancellation_fee": None,
                                "URL": size_url
                            }

                            self.log(f"  ✓ {size}m³: {price}€")
                            yield product

                    except Exception as e:
                        self.log(f"  ⚠️ Fehler bei Größe {size_code}: {e}")
                        continue

            except Exception as e:
                self.log(f"  ❌ Fehler bei {waste_type}: {e}")
                continue

        self.log(f"\n{'='*80}")
        self.log(f"✓ Gesamt gescrapt: {total_products} Produkte")
        self.log(f"{'='*80}\n")

    def _accept_cookies(self):
        """Akzeptiert Cookie-Banner falls vorhanden."""
        try:
            cookie_buttons = self.driver.find_elements(
                By.XPATH,
                "//button[contains(text(), 'Akzeptieren')] | //button[contains(text(), 'akzeptieren')] | //a[contains(text(), 'Akzeptieren')]"
            )
            for btn in cookie_buttons:
                if btn.is_displayed():
                    self.driver.execute_script("arguments[0].click();", btn)
                    sleep(1)
                    return True
        except Exception:
            pass
        return False

    def _find_product_id(self, url_slug):
        """Findet die Produkt-ID aus dem Absetzcontainer-Link."""
        try:
            # Finde Absetzcontainer-Link auf der Seite
            container_links = self.driver.find_elements(
                By.CSS_SELECTOR,
                "a[href*='absetzcontainer']"
            )

            for link in container_links:
                href = link.get_attribute("href") or ""
                if "absetzcontainer" in href.lower() and "hannover" in href.lower():
                    # Extrahiere Produkt-ID aus URL (z.B. cs-h-1011-m07 -> 1011)
                    match = re.search(r'cs-h-(\d+)-m\d+', href)
                    if match:
                        return match.group(1)

            # Fallback: Versuche Link zu klicken und URL zu prüfen
            for link in container_links:
                href = link.get_attribute("href") or ""
                text = link.text.lower()
                if "absetzcontainer" in text or "3-10" in text or "3 - 10" in text:
                    self.driver.get(href)
                    sleep(2)
                    current_url = self.driver.current_url
                    match = re.search(r'cs-h-(\d+)-m\d+', current_url)
                    if match:
                        return match.group(1)

        except Exception as e:
            self.log(f"  ⚠️ Fehler bei Produkt-ID Suche: {e}")

        return None

    def _get_current_price(self):
        """Extrahiert den aktuell angezeigten Preis."""
        try:
            price_selectors = [
                ".product-price",
                ".price",
                ".woocommerce-Price-amount",
                "[class*='price']",
                "span.amount",
            ]

            for selector in price_selectors:
                try:
                    price_elems = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    for price_elem in price_elems:
                        if price_elem.is_displayed():
                            price_text = price_elem.text.strip()
                            # Preis extrahieren
                            price_match = re.search(r'([\d.,]+)\s*€?', price_text)
                            if price_match:
                                price = price_match.group(1)
                                # Tausendertrennzeichen entfernen
                                if '.' in price and ',' in price:
                                    price = price.replace('.', '')
                                # Prüfe ob plausibel (> 100€)
                                try:
                                    price_val = float(price.replace(',', '.'))
                                    if price_val > 100:
                                        return price
                                except ValueError:
                                    pass
                except Exception:
                    continue

            # Fallback: Suche im gesamten Text
            body = self.driver.find_element(By.TAG_NAME, "body")
            text = body.text
            price_match = re.search(r'(\d{2,3}[.,]\d{2})\s*€', text)
            if price_match:
                return price_match.group(1)

        except Exception:
            pass
        return None
