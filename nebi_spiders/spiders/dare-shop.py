 



import logging
import re
from time import sleep

from scrapy import Spider
from scrapy.selector import Selector

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, StaleElementReferenceException


class DareShopProductsSpider(Spider):
    name = "dare-shop-products"
    allowed_domains = ["www.dare-shop.de", "dare-shop.de"]

    # Nur funktionierende Produkt-URLs (Status 200)
    start_urls = [
        # Baumischabfall
        "https://www.dare-shop.de/container-bestellen/25/absetzcontainer-fuer-baumischabfall-in-berlin?c=7",
        "https://www.dare-shop.de/container-bestellen/30/abrollcontainer-fuer-baumischabfall-in-berlin?c=7",

        # Bauschutt
        "https://www.dare-shop.de/container-bestellen/27/absetzcontainer-fuer-bauschutt-in-berlin?c=7",

        # Beton
        "https://www.dare-shop.de/container-bestellen/47/absetzcontainer-fuer-beton-in-berlin?c=7",

        # Boden
        "https://www.dare-shop.de/container-bestellen/46/absetzcontainer-fuer-boden-in-berlin",

        # Gartenabfall
        "https://www.dare-shop.de/container-bestellen/43/absetzcontainer-fuer-gartenabfall-in-berlin?c=7",
        "https://www.dare-shop.de/container-bestellen/42/abrollcontainer-fuer-gartenabfall-in-berlin?c=7",

        # Gewerbeabfall
        "https://www.dare-shop.de/container-bestellen/44/absetzcontainer-fuer-gewerbeabfall-in-berlin?c=7",
        "https://www.dare-shop.de/container-bestellen/45/abrollcontainer-fuer-gewerbeabfall-in-berlin?c=7",

        # Gipsbaustoffe
        "https://www.dare-shop.de/container-bestellen/26/absetzcontainer-fuer-gipsbaustoffe-in-berlin?c=7",
        "https://www.dare-shop.de/container-bestellen/28/abrollcontainer-fuer-gipsbaustoffe-in-berlin?c=7",

        # Holz A1–3 (unbehandelt)
        "https://www.dare-shop.de/container-bestellen/37/absetzcontainer-fuer-holz-a1-3-in-berlin?c=7",
        "https://www.dare-shop.de/container-bestellen/40/abrollcontainer-fuer-holz-a1-3-in-berlin?c=7",

        # Holz A4 (behandelt)
        "https://www.dare-shop.de/container-bestellen/38/absetzcontainer-fuer-holz-a4-in-berlin?c=7",
        "https://www.dare-shop.de/container-bestellen/39/abrollcontainer-fuer-holz-a4-in-berlin?c=7",

        # Sperrmüll
        "https://www.dare-shop.de/container-bestellen/49/absetzcontainer-fuer-sperrmuell-in-berlin?c=7",
        "https://www.dare-shop.de/container-bestellen/50/abrollcontainer-fuer-sperrmuell-in-berlin?c=7",
    ]

    def __init__(self):
        logging.getLogger("selenium").setLevel(logging.WARNING)
        logging.getLogger("urllib3").setLevel(logging.WARNING)

        self.driver = webdriver.Chrome()
        self.driver.maximize_window()

        # Dynamische Werte aus AGB holen
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
        Holt dynamische Werte von der AGB-Seite:
        - max_rental_period: Maximale Mietdauer in Tagen
        - fee_after_max: Gebühr pro Tag nach Ablauf (falls verfügbar)
        - cancellation_fee: Stornogebühr (falls verfügbar)
        """
        self.log("Hole dynamische Werte von AGB-Seite...")

        try:
            self.driver.get("https://www.dare-shop.de/agb")
            sleep(2)

            sel = Selector(text=self.driver.page_source)

            # Suche nach "Mietzeit von X Tagen" in §4
            agb_text = sel.xpath('//text()').getall()
            agb_full_text = " ".join(agb_text)

            # Extrahiere Mietzeit (z.B. "14 Tagen")
            rental_match = re.search(r'Mietzeit von (\d+) Tagen', agb_full_text)
            max_rental_period = rental_match.group(1) if rental_match else "14"

            # Extrahiere Wartezeit (z.B. "15 Minuten")
            wait_match = re.search(r'Wartezeit von (\d+) Minuten', agb_full_text)
            wait_time = wait_match.group(1) if wait_match else "15"

            self.log(f"✓ AGB-Werte geladen: Mietzeit={max_rental_period} Tage, Wartezeit={wait_time} Min")

            return {
                "max_rental_period": max_rental_period,
                "wait_time": wait_time,
                # Diese Werte stehen nicht in AGB, bleiben fest codiert:
                "fee_after_max": "5",  # Preis nicht in AGB angegeben
                "cancellation_fee": "135",  # Nicht in AGB erwähnt
            }

        except Exception as e:
            self.log(f"⚠️ Fehler beim Laden der AGB: {e}. Verwende Standardwerte.")
            return {
                "max_rental_period": "14",
                "wait_time": "15",
                "fee_after_max": "5",
                "cancellation_fee": "135",
            }

    # ---------------------------------------------------------
    # 1) Jede Produktseite nacheinander scrapen
    # ---------------------------------------------------------
    def parse(self, response):
        url = response.url
        self.log(f"\n{'='*80}")
        self.log(f"Starte Produktseite: {url}")
        self.log(f"{'='*80}\n")

        # Seite mit Selenium öffnen
        self.driver.get(url)
        sleep(2)

        # Cookie-Banner wegklicken (falls noch da)
        try:
            cookie_button = WebDriverWait(self.driver, 5).until(
                EC.element_to_be_clickable(
                    (By.XPATH, '//button[contains(., "Alle akzeptieren")]')
                )
            )
            cookie_button.click()
            self.log("Cookie-Banner akzeptiert.")
            sleep(1)
        except Exception:
            self.log("Cookie-Banner nicht gefunden oder bereits akzeptiert.")

        # aktuelles HTML holen
        sel = Selector(text=self.driver.page_source)

        # Titel
        title = (sel.xpath("//h1/text()").get() or "").strip()
        if not title:
            self.log("Kein Titel gefunden – breche für diese URL ab.")
            return

        # Abfallart aus Titel ableiten
        waste_type = (
            title.replace("Absetzcontainer für ", "")
            .replace("Abrollcontainer für ", "")
            .replace(" in Berlin", "")
            .strip()
        )

        # Dropdown "Größe" finden (Option 1: wirklich klicken)
        try:
            select_el = self.driver.find_element(
                By.XPATH,
                '//p[contains(@class,"configurator--label") and contains(., "Größe")]/following::select[1]'
            )
        except Exception:
            self.log("⚠️ Kein Größen-Dropdown gefunden – ein Eintrag ohne Größen.")
            # Preis direkt aus der Seite lesen
            sel = Selector(text=self.driver.page_source)
            price = self._extract_price(sel)
            size = ""
            current_url = self.driver.current_url
            item = self._build_item(title, waste_type, size, price, current_url)
            self.log(
                f"✓ ITEM: type={waste_type}, size={size}, price={price}, url={current_url}"
            )
            yield item
            self.log(f"Produktseite abgeschlossen: {title}\n")
            return

        select = Select(select_el)
        options_count = len(select.options)
        self.log(f"Gefunden: {options_count} Größen-Optionen")

        # -------------------------------------------------
        # Für JEDES Option-Element: klicken → warten → Preis
        # -------------------------------------------------
        for idx in range(options_count):
            # Select-Element und Optionen jedes Mal neu holen, um StaleElement zu vermeiden
            select_el = self.driver.find_element(
                By.XPATH,
                '//p[contains(@class,"configurator--label") and contains(., "Größe")]/following::select[1]'
            )
            select = Select(select_el)
            opt = select.options[idx]
            size_text = opt.text.strip()

            # Größe aus Text: "3 cbm" → "3"
            size_match = re.search(r"(\d+(?:[.,]\d+)?)\s*cbm", size_text)
            size = size_match.group(1) if size_match else size_text

            self.log(f"Verarbeite Option {idx+1}/{options_count}: {size_text}")

            # Aktuellen Preis vor dem Klicken holen
            sel_before = Selector(text=self.driver.page_source)
            price_before = self._extract_price(sel_before)
            self.log(f"Preis vor Auswahl: {price_before}")

            # Option anklicken über select_by_index (robuster)
            select.select_by_index(idx)
            sleep(0.5)

            # Warten, bis sich der Preis ändert (max 10 Sekunden)
            price_changed = False
            for attempt in range(20):  # 20 x 0.5s = 10 Sekunden
                sleep(0.5)
                sel = Selector(text=self.driver.page_source)
                price = self._extract_price(sel)

                if price and price != price_before:
                    price_changed = True
                    self.log(f"Preis aktualisiert nach {(attempt+1)*0.5}s: {price}")
                    break

            if not price_changed:
                self.log(f"WARNUNG: Preis hat sich nicht geändert für Größe {size}! Verwende: {price}")

            # Zusätzlich auf Artikelnummer warten
            try:
                WebDriverWait(self.driver, 3).until(
                    EC.presence_of_element_located(
                        (By.XPATH, '//input[@type="hidden" and contains(@value, "CS-")]')
                    )
                )
            except TimeoutException:
                pass

            sleep(0.5)  # kleine Extra-Pause

            sel = Selector(text=self.driver.page_source)
            current_url = self.driver.current_url
            price = self._extract_price(sel)

            item = self._build_item(title, waste_type, size, price, current_url)
            self.log(
                f"✓ ITEM: type={waste_type}, size={size}, price={price}, url={current_url}"
            )
            yield item

        self.log(f"\nProduktseite abgeschlossen: {title} ({options_count} Größen)\n")

    # ---------------------------------------------------------
    # Hilfsfunktion: Preis aus dem HTML ziehen
    # ---------------------------------------------------------
    def _extract_price(self, sel: Selector) -> str:
        """
        Versucht verschiedene Selektoren, um den aktuellen Preis zu finden.
        """
        price = ""

        # Methode 1: Preis aus dem sichtbaren Preis-Bereich
        # Typische Klassen: product--price, price--content, etc.
        price_candidates = sel.xpath(
            '//span[contains(@class, "price--content")]//text() | '
            '//div[contains(@class, "product--price")]//text() | '
            '//span[@itemprop="price"]//text()'
        ).getall()

        for candidate in price_candidates:
            candidate = candidate.strip()
            # Muster für 726,00 oder 1.910,50 etc.
            m = re.search(r'(\d{1,3}(?:\.\d{3})*,\d{2})', candidate)
            if m:
                price = m.group(1)
                break

        # Methode 2: Falls nicht gefunden, erste € Erwähnung
        if not price:
            price_text = sel.xpath(
                'normalize-space((//text()[contains(., "€")])[1])'
            ).get()

            if price_text:
                m = re.search(r'(\d{1,3}(?:\.\d{3})*,\d{2})', price_text)
                if m:
                    price = m.group(1)

        # Methode 3: meta tag als Fallback
        if not price:
            meta_price = sel.xpath(
                '//meta[@property="product:price"]/@content'
            ).get()
            if meta_price:
                price = meta_price.strip()

        return price

    # ---------------------------------------------------------
    # Hilfsfunktion: Item bauen
    # ---------------------------------------------------------
    def _build_item(
        self,
        title: str,
        waste_type: str,
        size: str,
        price: str,
        current_url: str,
    ) -> dict:
        return {
            "source": "dare-shop.de",
            "title": title,
            "type": waste_type,
            "city": "Berlin",
            "size": size,
            "price": price,
            "lid_price": "kostenlos nur, wenn verfügbar",
            "arrival_price": "free",
            "departure_price": "free",
            "max_rental_period": self.agb_values["max_rental_period"],
            "fee_after_max": self.agb_values["fee_after_max"],
            "cancellation_fee": self.agb_values["cancellation_fee"],
            "URL": current_url,
        }
