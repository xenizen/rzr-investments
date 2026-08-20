import requests

# Alpaca Creds
alpaca_api_key = "PKFNAWGSHU4YSYWVHARMH54SRG"
alpaca_secret_key = "5fg9VuQNczvVhbb6x84Qxo87rM92rxU9A9srEjJ3CN1a"
Stock = "MSFT"

url = "https://data.sandbox.alpaca.markets/v2/stocks/trades/latest?symbols=MSFT&feed=sip&currency=USD"

headers = {
    "accept": "application/json",
    "APCA-API-KEY-ID": "PKFNAWGSHU4YSYWVHARMH54SRG",
    "APCA-API-SECRET-KEY": "5fg9VuQNczvVhbb6x84Qxo87rM92rxU9A9srEjJ3CN1a"
}

response = requests.get(url, headers=headers)

print(response.text)
