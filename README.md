# Automated Fuel Price Tracker

A daily data pipeline that downloads the official Italian fuel price open data (MIMIT – Ministry of Enterprises and Made in Italy), finds the **cheapest self-service diesel within 20 km** of a given location and sends the top 5 stations as a **Telegram message**.

It runs automatically every day on **GitHub Actions**: no computer needs to be switched on.

---

## What it does

1. **Extract** – downloads two CSV files published daily by MIMIT:
   - `prezzo_alle_8.csv` – prices in force at 8:00 a.m.
   - `anagrafica_impianti_attivi.csv` – registry of active fuel stations (name, brand, address, coordinates)
2. **Clean**
   - repairs the station registry, where some station names contain the column separator (`" | gestori.prezzibenzina.it"`) and would otherwise break the rows
   - discards prices not updated in the last 7 days
3. **Transform**
   - joins prices and stations on `idImpianto`
   - keeps only stations inside a ~20 km square around the reference point
   - keeps only **diesel, self-service**
   - **anomaly filter**: prices more than 20% below the local median are treated as input errors, excluded and written to the log (real low prices stay within about -10%, the errors observed were around -30%)
   - computes the straight-line distance of each station (degrees converted to km, then Pythagoras)
4. **Load / Notify** – sorts by **price, then distance** (so at equal price the closest station comes first) and sends the top 5 to Telegram in a single message.

### Example message

```
1)PREZZO: 2.189 € - Distanza: 10.17 km - Comune: VICENZA - Bandiera: Auchan - Indirizzo: VIALE DEL SOLE 300 36100 - Data comunicazione: 2026-10-12 09:30:13
2)PREZZO: 2.19 € - Distanza: 1.85 km - Comune: CASTELGOMBERTO - Bandiera: Agip Eni - Indirizzo: VIA PECORI GIRALDI 63, 36070 - Data comunicazione: 2026-10-12 07:42:35
...
```

---

## Tech stack

- **Python 3.14**
- **pandas** – cleaning, filtering, joining, sorting
- **requests** – data download and Telegram Bot API
- **python-dotenv** – local secrets management
- **logging** – run history, discarded prices, errors
- **GitHub Actions** – daily scheduling, secrets stored as repository secrets

---

## Reliability and security

- Every HTTP request has a **timeout** and is checked with `raise_for_status()`.
- If the MIMIT download fails, the error is logged and the script stops instead of working on missing data.
- Telegram errors are logged **without the request URL**, so the bot token never ends up in the log file. HTTP errors log the status code (e.g. `404`), network errors log only the error type (e.g. `ConnectionError`).
- No credentials in the code: the bot token and chat id are read from environment variables (a local `.env` file outside the project, or GitHub Secrets).
- File paths are built from the script's own location (`__file__`), so the script works no matter which folder it is launched from.

---

## Run it locally

```bash
pip install -r requirements.txt
python prezzi_carburante.py
```

Create a `.env` file in `~/Secret/.env` (outside the repository):

```
TELEGRAM_BOT=your_bot_token
CHAT_ID=your_chat_id
```

The log is written to `script_prezzi_carburante.log`, next to the script.

---

## Automation (GitHub Actions)

The workflow in `.github/workflows/` runs:

- **every day at 07:30 UTC** (09:30 Italian summer time, 08:30 winter time), always after the 8:00 a.m. price file is available
- **manually**, from the *Actions* tab (`workflow_dispatch`)

Required repository secrets: `TELEGRAM_BOT`, `CHAT_ID`.

---

## Configuration

Inside `prezzi_carburante.py`:

| Variable | Meaning | Default |
|---|---|---|
| `lat`, `lon` | reference point | Trissino (VI) |
| `raggio_km` | search radius | `20` |
| `SOGLIA_ANOMALIA` | max % below the median before a price is discarded | `-20` |

---

## Known limitations

- Distance is a **straight-line** approximation, not driving distance (accurate to a few hundred metres within 20 km).
- GitHub Actions does not guarantee the exact start time of scheduled runs: on the free plan they can be delayed.
- On GitHub Actions the log file lives on a temporary machine and is not kept after the run.

## Roadmap

- [ ] Check the extraction date in the MIMIT file and skip the run if the data is not from today
- [ ] Keep the log available after GitHub Actions runs
- [ ] Store daily prices in SQLite to build a price history
- [ ] Translate variable names and comments to English

---

Data source: [MIMIT – Open data carburanti](https://www.mimit.gov.it/it/open-data/elenco-dataset/carburanti-prezzi-praticati-e-anagrafica-degli-impianti)
