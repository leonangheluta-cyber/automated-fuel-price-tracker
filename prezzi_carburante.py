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
CARTELLA=os.path.dirname(os.path.abspath(__file__))
PERCORSO_LOG=os.path.join(CARTELLA, "script_prezzi_carburante.log")
PERCORSO_CSV=os.path.join(CARTELLA, "anagrafica_impianti_attivi_ok.csv")
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s", filename=PERCORSO_LOG)

# %%
url_prezzi="https://www.mimit.gov.it/images/exportCSV/prezzo_alle_8.csv"
url_impianti="https://www.mimit.gov.it/images/exportCSV/anagrafica_impianti_attivi.csv"
try:
    richiesta_prezzi=requests.get(url_prezzi, timeout=15)
    richiesta_impianti=requests.get(url_impianti, timeout=15)
    richiesta_impianti.raise_for_status()
    richiesta_prezzi.raise_for_status()
except requests.exceptions.RequestException as error:
    logging.error(f"Richiesta file fallita: {error}")
    sys.exit(1)

# %%
richiesta_impianti.encoding="utf-8"
richiesta_prezzi.encoding="utf-8"
testo_impianti = richiesta_impianti.text
testo_prezzi = richiesta_prezzi.text
righe_impianti=testo_impianti.splitlines()

# %%
with open(PERCORSO_CSV, "w", encoding="utf-8") as uscita:
    for numero, riga in enumerate(righe_impianti, start=1):
        riga=riga.replace(" | gestori.prezzibenzina.it", "")
        if numero==1:
            continue
        uscita.write(riga + "\n")   

# %%
impianti=pd.read_csv(PERCORSO_CSV, sep="|")
prezzi=pd.read_csv(io.StringIO(testo_prezzi), sep="|", skiprows=1)

# %%
prezzi["dtComu"]=pd.to_datetime(prezzi["dtComu"], dayfirst=True)

# %%
data=datetime.now().replace(microsecond=0, second=0, minute=0, hour=0)
ultima_data=prezzi["dtComu"].max().replace(microsecond=0, second=0, minute=0, hour=0)
scelta_data=min(data, ultima_data)
data_limite=scelta_data-timedelta(days=7)

# %%
aggiornato=prezzi["dtComu"]>=data_limite
prezzi_aggiornati=prezzi[aggiornato]
prezzi_scartati=prezzi[~aggiornato]

# %%
unione=pd.merge(prezzi_aggiornati, impianti, on="idImpianto", how="left")

# %%
raggio_km=20
lat=45.5548
lon=11.378902
calcolo_lat=raggio_km/111
calcolo_long=raggio_km/78
lat_min=lat-calcolo_lat
lat_max=lat+calcolo_lat
lon_min=lon-calcolo_long
lon_max=lon+calcolo_long

# %%
distributori_entro_raggio=unione[(unione["Latitudine"]<lat_max) & (unione["Latitudine"]>lat_min) & (unione["Longitudine"]<lon_max) & (unione["Longitudine"]>lon_min)]

# %%
carburante=distributori_entro_raggio[(distributori_entro_raggio["descCarburante"]=="Gasolio") & (distributori_entro_raggio["isSelf"]==1)]

# %%
#Scarto i prezzi oltre il 20% sotto la mediana del quadrato:
#i prezzi veri più bassi stanno entro circa il -10% (anche durante un calo dei prezzi),
#gli errori di inserimento visti finora sono attorno al -30%.
SOGLIA_ANOMALIA=-20
mediana_diesel=carburante["prezzo"].median()
conversione_percentuale=((carburante["prezzo"]-mediana_diesel)/mediana_diesel)*100
carburante["scostamento"]=conversione_percentuale

# %%

df_prezzi_buoni=carburante[carburante["scostamento"]>=SOGLIA_ANOMALIA]
df_prezzi_scartati=carburante[carburante["scostamento"]<SOGLIA_ANOMALIA]

# %%
for indice, riga in df_prezzi_scartati.iterrows():
    logging.warning(f"Prezzo scartato -> impianto {riga["idImpianto"]} ({riga["Gestore"]}, {riga["Bandiera"]}), prezzo {riga["prezzo"]} €, mediana {mediana_diesel} €, scostamento {round(riga["scostamento"], 2)} %, comunicato il {riga["dtComu"]}")
logging.info(f"Controllo anomalie: {df_prezzi_scartati.shape[0]} scartati su {carburante.shape[0]}")

# %%
cateto_lat=(df_prezzi_buoni["Latitudine"]-lat)*111
cateto_lon=(df_prezzi_buoni["Longitudine"]-lon)*78
calcolo_ipotenusa=(cateto_lat**2+cateto_lon**2)**0.5
df_prezzi_buoni["distanza"]=round(calcolo_ipotenusa,2 )

# %%
primi_5=df_prezzi_buoni.sort_values(["prezzo", "distanza"]).head(5)
primi_5=primi_5[["prezzo", "distanza", "Comune", "Bandiera", "Indirizzo", "dtComu" ]]

# %%
testo=""
i=0
for numero, riga in primi_5.iterrows():
    i+=1
    testo+=f"{i})PREZZO: {riga["prezzo"]} € - Distanza: {riga["distanza"]} km - Comune: {riga["Comune"]} - Bandiera: {riga["Bandiera"]} - Indirizzo: {riga["Indirizzo"]} - Data comunicazione: {riga["dtComu"]}\n"

# %%
path_env=Path.home()/ "Secret" / ".env"
load_dotenv(dotenv_path=path_env)
telegram_bot=os.environ.get("TELEGRAM_BOT")
chat_id=os.environ.get("CHAT_ID")

# %%
url = f"https://api.telegram.org/bot{telegram_bot}/sendMessage"
try:
    send_message=requests.get(url, params={"chat_id": chat_id, "text": testo}, timeout=10)
    send_message.raise_for_status()
    logging.info("Messaggio partito")
except requests.exceptions.HTTPError:
    logging.warning(f"Errore token/chat id: {send_message.status_code}")
except requests.exceptions.RequestException as error:
    logging.warning(f"Errore: {type(error).__name__}")


