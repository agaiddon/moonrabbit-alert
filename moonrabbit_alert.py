import os
import json
import time
import requests
from web3 import Web3

RPC_URL = "https://evm.moonrabbit.com"

PAIR_ADDRESS = "0x0000000000000000000000000000000000000000"  # à remplacer si besoin

LOW_THRESHOLD_10M = 10_000_000
LOW_THRESHOLD_9M = 9_000_000

LEVELS = {
    "9m": 9_000_000,
    "10m": 10_000_000,
    "11m": 11_000_000,
    "12m": 12_000_000
}

STATE_FILE = "alert_state.json"


def load_state():
    if not os.path.exists(STATE_FILE):
        return {
            "below_10m": False,
            "below_9m": False,
            "levels_triggered": {
                "9m": False,
                "10m": False,
                "11m": False,
                "12m": False
            }
        }
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
    """
    ⚠️ À remplacer par ton vrai calcul on-chain
    Pour l'instant on simule une valeur
    """
    return 9_100_000


def main():
    w3 = connect_web3_with_retries(RPC_URL)

    state = load_state()

    out_waaa = get_price_dummy()

    # --- ALERTES SOUS SEUILS ---
    is_below_10m = out_waaa < LOW_THRESHOLD_10M
    is_below_9m = out_waaa < LOW_THRESHOLD_9M

    if is_below_10m and not state["below_10m"]:
        telegram_send(f"⚠️ Passage sous 10M : ~{out_waaa:,} WAAA")

    if is_below_9m and not state["below_9m"]:
        telegram_send(f"⚠️ Passage sous 9M : ~{out_waaa:,} WAAA")

    # --- ALERTES AU-DESSUS ---
    for level_name, threshold in LEVELS.items():
        already_triggered = state["levels_triggered"][level_name]

        if out_waaa >= threshold and not already_triggered:
            telegram_send(f"🔔 Passage au-dessus de {threshold:,} WAAA : ~{out_waaa:,}")
            state["levels_triggered"][level_name] = True

        elif out_waaa < threshold:
            state["levels_triggered"][level_name] = False

    # --- UPDATE STATE ---
    state["below_10m"] = is_below_10m
    state["below_9m"] = is_below_9m

    save_state(state)


if __name__ == "__main__":
    main()