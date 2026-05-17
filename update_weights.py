"""
update_weights.py
Lädt Ländergewichtungen direkt von iShares (BlackRock) und berechnet
die portfoliogewichteten Anteile je Land.

Endpoint: https://www.ishares.com/uk/individual/en/products/{PRODUCT_ID}/1467271812596.ajax
          ?tab=country&fileType=json

Wird wöchentlich via GitHub Actions ausgeführt.
"""

import json
import os
import time
import requests
from datetime import datetime

# ── Portfolio-Konfiguration (Portfolio-Anteil in Dezimalform) ──────────────────
# Wenn du den Sparplan änderst, hier anpassen.
PORTFOLIO = {
    "SXR8":  {"isin": "IE00B5BMR087", "product_id": "253743", "pct": 0.200},  # iShares Core S&P 500
    "CPXJ":  {"isin": "IE00B52MJY50", "product_id": "253735", "pct": 0.150},  # MSCI Pacific ex-Japan
    "CSKR":  {"isin": "IE00B5W4TY14", "product_id": "253742", "pct": 0.026},  # MSCI Korea (Product-ID korrigiert)
    "IJPA":  {"isin": "IE00B4L5YX21", "product_id": "251929", "pct": 0.024},  # MSCI Japan IMI (ISIN korrigiert)
    "WHCS":  {"isin": "IE00B4L5Y983", "product_id": "251882", "pct": 0.140},  # MSCI World Health Care
    "AGED":  {"isin": "IE00BYZK4669", "product_id": "284218", "pct": 0.050},  # Ageing Population
    "EIMI":  {"isin": "IE00BKM4GZ66", "product_id": "264659", "pct": 0.140},  # MSCI EM IMI
    # Edelmetalle: keine Länder-Tab → Fallback auf Mining-Daten (statisch)
    "PHAG":  {"isin": "JE00B1VS3333", "product_id": None,     "pct": 0.060},  # Physical Silver
    "PHPT":  {"isin": "JE00B1VS2W53", "product_id": None,     "pct": 0.046},  # Physical Platinum
    "COPA":  {"isin": "GB00B15KXQ89", "product_id": None,     "pct": 0.044},  # Copper ETC (ISIN korrigiert)
    # Einzelpositionen
    "ALV":   {"isin": "DE0008404005", "product_id": None,     "pct": 0.070},  # Allianz SE → Deutschland
    "ISF":   {"isin": "IE0005042456", "product_id": "251882", "pct": 0.050},  # FTSE 100 → UK
}

# ── Statische Fallback-Daten für Edelmetalle (USGS 2025, Förderländer) ────────
EDELMETALL_FALLBACK = {
    "PHAG": {  # Silber-Förderung
        "Mexico": 24.0, "Peru": 15.0, "China": 13.0, "Russia": 8.0,
        "Chile": 5.0, "Australia": 5.0, "Poland": 5.0, "Bolivia": 5.0,
        "Argentina": 5.0, "Other": 15.0
    },
    "PHPT": {  # Platin-Förderung
        "South Africa": 73.0, "Russia": 11.0, "Zimbabwe": 8.0,
        "Canada": 4.0, "United States": 2.0, "Other": 2.0
    },
    "COPA": {  # Kupfer-Förderung
        "Chile": 27.0, "Peru": 10.0, "Congo, Dem. Rep.": 10.0,
        "China": 8.0, "United States": 6.0, "Australia": 5.0,
        "Zambia": 4.0, "Indonesia": 4.0, "Mexico": 3.0, "Other": 23.0
    }
}

EINZELPOSITIONEN_FALLBACK = {
    "ALV": {"Germany": 100.0},
    "ISF": {"United Kingdom": 100.0},
}

# ── iShares Endpoint-Konfiguration ────────────────────────────────────────────
ISHARES_BASE = "https://www.ishares.com/uk/individual/en/products"
AJAX_SUFFIX  = "1467271812596.ajax"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Linux; Android 13; Pixel 7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Mobile Safari/537.36"
    ),
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
    "Referer": "https://www.ishares.com/",
    "X-Requested-With": "XMLHttpRequest",
}

def fetch_country_weights(product_id: str, ticker: str) -> dict | None:
    """Ruft Ländergewichtungen vom iShares AJAX-Endpoint ab.
    Gibt dict {country_name: pct} zurück oder None bei Fehler."""
    url = f"{ISHARES_BASE}/{product_id}/{AJAX_SUFFIX}?tab=country&fileType=json"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            print(f"  [{ticker}] HTTP {resp.status_code} — überspringe")
            return None

        data = resp.json()

        # iShares gibt {'tableData': {'columns': [...], 'data': [...]}} zurück
        # Spaltennamen variieren, typisch: ['Country', 'Weighting']
        table = data.get("tableData") or data.get("data")
        if not table:
            print(f"  [{ticker}] Kein tableData in Response")
            return None

        columns = [c.get("label", c.get("name", "")) for c in table.get("columns", [])]
        rows    = table.get("data", [])

        # Finde die Spalten-Indizes für Land und Gewichtung
        country_idx = next((i for i, c in enumerate(columns)
                            if "country" in c.lower() or "land" in c.lower()), None)
        weight_idx  = next((i for i, c in enumerate(columns)
                            if "weight" in c.lower() or "anteil" in c.lower()
                            or "%" in c), None)

        if country_idx is None or weight_idx is None:
            print(f"  [{ticker}] Spalten nicht gefunden: {columns}")
            return None

        result = {}
        for row in rows:
            try:
                country = row[country_idx]
                weight  = float(str(row[weight_idx]).replace("%", "").replace(",", "."))
                if country and weight > 0:
                    result[country] = result.get(country, 0) + weight
            except (ValueError, IndexError):
                continue

        print(f"  [{ticker}] OK — {len(result)} Länder geladen")
        return result if result else None

    except requests.RequestException as e:
        print(f"  [{ticker}] Netzwerkfehler: {e}")
        return None
    except (json.JSONDecodeError, KeyError) as e:
        print(f"  [{ticker}] Parse-Fehler: {e}")
        return None


def calculate_portfolio_weights() -> list:
    """Berechnet die portfoliogewichteten Länderanteile aus allen Positionen."""
    global_weights = {}  # {country: {pct: float, via: [tickers]}}

    for ticker, config in PORTFOLIO.items():
        portfolio_pct = config["pct"]
        country_data  = None

        # 1. iShares Endpoint versuchen
        if config.get("product_id"):
            print(f"Lade {ticker} von iShares...")
            country_data = fetch_country_weights(config["product_id"], ticker)
            time.sleep(1.5)  # Rate-Limiting respektieren

        # 2. Fallback: Edelmetalle / Einzelpositionen
        if country_data is None:
            if ticker in EDELMETALL_FALLBACK:
                print(f"  [{ticker}] Nutze Edelmetall-Fallback (USGS-Daten)")
                country_data = EDELMETALL_FALLBACK[ticker]
            elif ticker in EINZELPOSITIONEN_FALLBACK:
                print(f"  [{ticker}] Nutze Einzelposition-Fallback")
                country_data = EINZELPOSITIONEN_FALLBACK[ticker]
            else:
                print(f"  [{ticker}] Kein Fallback — überspringe")
                continue

        # 3. Portfoliogewichtung berechnen
        total_pct = sum(v for v in country_data.values() if v > 0)
        for country, etf_pct in country_data.items():
            if country.lower() in ("other", "sonstige", "-", ""):
                continue  # "Other" ignorieren
            # Normalisieren falls die Summe nicht 100% ist
            normalized = (etf_pct / total_pct) * 100 if total_pct > 0 else etf_pct
            weighted   = (normalized / 100) * portfolio_pct * 100  # → % vom Gesamtportfolio

            if country not in global_weights:
                global_weights[country] = {"pct_gesamt": 0.0, "via": []}
            global_weights[country]["pct_gesamt"] += weighted
            if ticker not in global_weights[country]["via"]:
                global_weights[country]["via"].append(ticker)

    # In Liste umwandeln und sortieren
    output = [
        {
            "land":        country,
            "pct_gesamt":  round(data["pct_gesamt"], 2),
            "via":         data["via"],
            "last_updated": datetime.now().strftime("%Y-%m-%d")
        }
        for country, data in global_weights.items()
        if data["pct_gesamt"] >= 0.05  # Länder unter 0.05% weglassen
    ]
    output.sort(key=lambda x: x["pct_gesamt"], reverse=True)
    return output


def load_existing(path: str) -> dict:
    """Lädt bestehende JSON als Fallback falls iShares nicht erreichbar."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


if __name__ == "__main__":
    OUTPUT_PATH = "data/geo_weights.json"
    os.makedirs("data", exist_ok=True)

    print(f"=== ETF Geo-Update gestartet ({datetime.now().strftime('%Y-%m-%d %H:%M')}) ===")
    existing = load_existing(OUTPUT_PATH)

    new_weights = calculate_portfolio_weights()

    if not new_weights:
        print("WARNUNG: Keine Daten geladen — behalte bestehende JSON.")
    else:
        result = {
            "_meta": {
                "last_updated":    datetime.now().strftime("%Y-%m-%d"),
                "total_positions": len(PORTFOLIO),
                "total_countries": len(new_weights),
                "note":            "pct_gesamt = Anteil am Portfolio. EUR = currentTotal × pct_gesamt / 100"
            },
            "countries": new_weights
        }
        with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"=== Fertig: {len(new_weights)} Länder in {OUTPUT_PATH} gespeichert ===")
