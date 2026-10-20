# %%
import requests
import sys
import pandas as pd
import io
from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime, timedelta
import os
import logging
FOLDER=os.path.dirname(os.path.abspath(__file__))
LOG_PATH=os.path.join(FOLDER, "script_prezzi_carburante.log")
CSV_PATH=os.path.join(FOLDER, "anagrafica_impianti_attivi_ok.csv")
handlers=[logging.StreamHandler(), logging.FileHandler(LOG_PATH)]
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s", handlers=handlers)


# %%
prices_url="https://www.mimit.gov.it/images/exportCSV/prezzo_alle_8.csv"
facilities_url="https://www.mimit.gov.it/images/exportCSV/anagrafica_impianti_attivi.csv"
try:
    prices_request=requests.get(prices_url, timeout=60)
    facilities_request=requests.get(facilities_url, timeout=60)
    facilities_request.raise_for_status()
    prices_request.raise_for_status()
except requests.exceptions.RequestException as error:
    logging.error(f"Request failed: {error}")
    sys.exit(1)

# %%
facilities_request.encoding="utf-8"
prices_request.encoding="utf-8"
facilities_text = facilities_request.text
prices_text = prices_request.text
facilities_lines=facilities_text.splitlines()

# %%
with open(CSV_PATH, "w", encoding="utf-8") as writer:
    for number, row in enumerate(facilities_lines, start=1):
        row=row.replace(" | gestori.prezzibenzina.it", "")
        if number==1:
            continue
        writer.write(row + "\n")   

# %%
facilities=pd.read_csv(CSV_PATH, sep="|")
prices=pd.read_csv(io.StringIO(prices_text), sep="|", skiprows=1)

# %%
prices["dtComu"]=pd.to_datetime(prices["dtComu"], dayfirst=True)

# %%
date=datetime.now().replace(microsecond=0, second=0, minute=0, hour=0)
last_date=prices["dtComu"].max().replace(microsecond=0, second=0, minute=0, hour=0)
date_choice=min(date, last_date)
limit_date=date_choice-timedelta(days=7)

# %%
date_mask=prices["dtComu"]>=limit_date
kept_prices=prices[date_mask]
discarded_prices=prices[~date_mask]

# %%
prices_merge=pd.merge(kept_prices, facilities, on="idImpianto", how="left")

# %%
km_radius=20
lat=45.5548
lon=11.378902
lat_calculation=km_radius/111
lon_calculation=km_radius/78
lat_min=lat-lat_calculation
lat_max=lat+lat_calculation
lon_min=lon-lon_calculation
lon_max=lon+lon_calculation

# %%
facilities_in_radius=prices_merge[(prices_merge["Latitudine"]<lat_max) & (prices_merge["Latitudine"]>lat_min) & (prices_merge["Longitudine"]<lon_max) & (prices_merge["Longitudine"]>lon_min)]

# %%
chosen_fuel=facilities_in_radius[(facilities_in_radius["descCarburante"]=="Gasolio") & (facilities_in_radius["isSelf"]==1)]

# %%
#I exclude prices that are more than 20% below the median of the updated dataset:
#the lowest genuine prices fall within approximately -10% (even during a price downturn),
#while the data entry errors observed so far are around -30%
anomaly_threshold=-20
median_diesel_price=chosen_fuel["prezzo"].median()
percentage_conversion=((chosen_fuel["prezzo"]-median_diesel_price)/median_diesel_price)*100
chosen_fuel["deviation"]=percentage_conversion

# %%

price_within_deviation=chosen_fuel[chosen_fuel["deviation"]>=anomaly_threshold]
price_out_deviation=chosen_fuel[chosen_fuel["deviation"]<anomaly_threshold]

# %%
path_env=Path.home()/"Secret"/".env"
load_dotenv(dotenv_path=path_env)
telegram_bot=os.environ.get("TELEGRAM_BOT")
chat_id=os.environ.get("CHAT_ID")
url = f"https://api.telegram.org/bot{telegram_bot}/sendMessage"
discarde_for_telegram=""
num=0
for i, row in price_out_deviation.iterrows():
    num+=1
    discarde_for_telegram+=f"{num}) Discarded price -> facility {row["idImpianto"]} ({row["Gestore"]}, {row["Bandiera"]}), price {row["prezzo"]} €, median {median_diesel_price} €, deviation {round(row["deviation"], 2)} %, date comunication {row["dtComu"]}\n"
logging.info(discarde_for_telegram)
logging.info(f"Anomaly checkup: {price_out_deviation.shape[0]} discarded out of {chosen_fuel.shape[0]}")

# %%
leg_lat=(price_within_deviation["Latitudine"]-lat)*111
leg_lon=(price_within_deviation["Longitudine"]-lon)*78
hypotenuse_calculation=(leg_lat**2+leg_lon**2)**0.5
price_within_deviation["distanza"]=round(hypotenuse_calculation,2 )

# %%
best_five_prices=price_within_deviation.sort_values(["prezzo", "distanza"]).head(5)
best_five_prices=best_five_prices[["prezzo", "distanza", "Comune", "Bandiera", "Indirizzo", "dtComu" ]]

# %%
text=""
i=0
for number, row in best_five_prices.iterrows():
    i+=1
    text+=f"{i}) PREZZO: {row["prezzo"]} € - Distanza: {row["distanza"]} km - Comune: {row["Comune"]} - Bandiera: {row["Bandiera"]} - Indirizzo: {row["Indirizzo"]} - Data comunicazione: {row["dtComu"]}\n"
    text=text.replace("- -", "")
# %%
try:
    send_message=requests.get(url, params={"chat_id": chat_id, "text": text}, timeout=10)
    send_message.raise_for_status()
    logging.info("Messaggio partito")
    if discarde_for_telegram:
        send_discarded_prices=requests.get(url, params={"chat_id": chat_id, "text": discarde_for_telegram}, timeout=10)
        send_discarded_prices.raise_for_status()
except requests.exceptions.HTTPError as error:
    logging.warning(f"HTTP error: {error.response.status_code}")
except requests.exceptions.RequestException as error:
    logging.warning(f"Errore: {type(error).__name__}")