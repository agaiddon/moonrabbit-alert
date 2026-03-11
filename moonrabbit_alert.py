import os
import json
import requests
from web3 import Web3

RPC_URL = "https://evm.moonrabbit.com"
PAIR_ADDRESS = "0x93361341D82c37437B49bc907bA0758e582D28a9"

WAAA_DECIMALS = 18
WUSDC_DECIMALS = 18

AMOUNT_IN_WUSDC = 2.0
LOW_THRESHOLD_WAAA = 10_000_000.0

LEVELS = {
    "9m": 9_000_000.0,
    "10m": 10_000_000.0,
    "11m": 11_000_000.0,
    "12m": 12_000_000.0
}

# Fee AMM supposée 0,30%
FEE_BPS = 30

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

PAIR_ABI = [
    {
        "constant": True,
        "inputs": [],
        "name": "getReserves",
        "outputs": [
            {"name": "_reserve0", "type": "uint112"},
            {"name": "_reserve1", "type": "uint112"},
            {"name": "_blockTimestampLast", "type": "uint32"},
        ],
        "type": "function",
    }
]

STATE_FILE = "state.json"


def load_state():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {
            "below_10m": False,
            "last_hourly_rate": None,
            "levels_triggered": {
                "9m": False,
                "10m": False,
                "11m": False,
                "12m": False
            }
        }


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def telegram_send(msg: str) -> None:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        raise RuntimeError("Variables Telegram manquantes (TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID).")

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    r = requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": msg}, timeout=20)
    r.raise_for_status()


def amount_out_v2(amount_in: int, reserve_in: int, reserve_out: int, fee_bps: int) -> int:
    amount_in_with_fee = amount_in * (10_000 - fee_bps)
    numerator = amount_in_with_fee * reserve_out
    denominator = reserve_in * 10_000 + amount_in_with_fee
    return numerator // denominator


def main():
    w3 = Web3(Web3.HTTPProvider(RPC_URL))
    if not w3.is_connected():
        raise RuntimeError("Connexion RPC impossible.")

    pair = w3.eth.contract(address=Web3.to_checksum_address(PAIR_ADDRESS), abi=PAIR_ABI)
    r0, r1, _ = pair.functions.getReserves().call()

    # token0=WAAA (r0), token1=wUSDC (r1)
    reserve_waaa_raw = int(r0)
    reserve_wusdc_raw = int(r1)

    amount_in_raw = int(AMOUNT_IN_WUSDC * (10 ** WUSDC_DECIMALS))
    out_raw = amount_out_v2(amount_in_raw, reserve_wusdc_raw, reserve_waaa_raw, fee_bps=FEE_BPS)
    out_waaa = out_raw / (10 ** WAAA_DECIMALS)

    line = f"2 wUSDC -> ~{out_waaa:,.0f} WAAA | reserves: WAAA={reserve_waaa_raw} wUSDC={reserve_wusdc_raw}"
    print(line)

    state = load_state()

    if "levels_triggered" not in state:
        state["levels_triggered"] = {
            "9m": False,
            "10m": False,
            "11m": False,
            "12m": False
        }

    is_below_10m = out_waaa < LOW_THRESHOLD_WAAA

    # Alerte spéciale si on passe sous 10M
    if is_below_10m and not state.get("below_10m", False):
        telegram_send("⚠️ Passage sous 10M : " + line)

    # Alertes de franchissement à la hausse
    for level_name, threshold in LEVELS.items():
        already_triggered = state["levels_triggered"].get(level_name, False)

        if out_waaa >= threshold and not already_triggered:
            telegram_send(f"🔔 Passage au-dessus de {threshold:,.0f} WAAA : " + line)
            state["levels_triggered"][level_name] = True

        elif out_waaa < threshold:
            state["levels_triggered"][level_name] = False

    # Mise à jour état seuil bas
    state["below_10m"] = is_below_10m

    save_state(state)


if __name__ == "__main__":
    main()
