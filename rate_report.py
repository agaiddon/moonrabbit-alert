import os
import json
import time
import requests
from web3 import Web3

RPC_URL = "https://evm.moonrabbit.com"

STATE_FILE = "hourly_state.json"


def load_state():
    if not os.path.exists(STATE_FILE):
        return {}
    with open(STATE_FILE, "r") as f:
        return json.load(f)


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)


def telegram_send(message):
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    requests.post(url, json={
        "chat_id": chat_id,
        "text": message
    })


def connect_web3_with_retries(rpc_url, retries=5, delay=5):
    for attempt in range(1, retries + 1):
        w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 20}))
        if w3.is_connected():
            return w3
        print(f"Tentative RPC {attempt}/{retries} échouée")
        if attempt < retries:
            time.sleep(delay)
    raise RuntimeError("Connexion RPC impossible après plusieurs tentatives.")


def get_price_dummy():
    return 9_100_000


def main():
    w3 = connect_web3_with_retries(RPC_URL)

    state = load_state()

    out_waaa = get_price_dummy()

    telegram_send(f"📈 Taux horaire : ~{out_waaa:,} WAAA")

    state["last_rate"] = out_waaa
    save_state(state)


if __name__ == "__main__":
    main()