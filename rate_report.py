import os
import json
import time
import requests
from web3 import Web3

RPC_URL = "https://evm.moonrabbit.com"
PAIR_ADDRESS = "0x93361341D82c37437B49bc907bA0758e582D28a9"

WAAA_DECIMALS = 18
WUSDC_DECIMALS = 18
AMOUNT_IN_WUSDC = 2.0
FEE_BPS = 30

VARIATION_THRESHOLD_PERCENT = 5.0
STATE_FILE = "hourly_state.json"

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


def load_state():
    default_state = {
        "last_hourly_rate": None,
    }

    if not os.path.exists(STATE_FILE):
        return default_state

    with open(STATE_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    for key, value in default_state.items():
        if key not in data:
            data[key] = value

    return data


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def telegram_send(message):
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    response = requests.post(
        url,
        json={"chat_id": chat_id, "text": message},
        timeout=20,
    )
    response.raise_for_status()


def connect_web3_with_retries(rpc_url, retries=5, delay=5):
    for attempt in range(1, retries + 1):
        try:
            w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 20}))
            if w3.is_connected():
                return w3
            print(f"Tentative RPC {attempt}/{retries} échouée : non connecté")
        except Exception as e:
            print(f"Tentative RPC {attempt}/{retries} échouée : {e}")

        if attempt < retries:
            time.sleep(delay)

    return None


def amount_out_v2(amount_in, reserve_in, reserve_out, fee_bps):
    amount_in_with_fee = amount_in * (10_000 - fee_bps)
    numerator = amount_in_with_fee * reserve_out
    denominator = reserve_in * 10_000 + amount_in_with_fee
    return numerator // denominator


def get_current_out_waaa():
    w3 = connect_web3_with_retries(RPC_URL)
    if w3 is None:
        return None

    try:
        pair = w3.eth.contract(address=Web3.to_checksum_address(PAIR_ADDRESS), abi=PAIR_ABI)
        reserve_waaa_raw, reserve_wusdc_raw, _ = pair.functions.getReserves().call()

        amount_in_raw = int(AMOUNT_IN_WUSDC * (10 ** WUSDC_DECIMALS))
        out_raw = amount_out_v2(
            amount_in_raw,
            int(reserve_wusdc_raw),
            int(reserve_waaa_raw),
            FEE_BPS,
        )
        out_waaa = out_raw / (10 ** WAAA_DECIMALS)

        return {
            "out_waaa": out_waaa,
            "reserve_waaa_raw": int(reserve_waaa_raw),
            "reserve_wusdc_raw": int(reserve_wusdc_raw),
        }

    except Exception as e:
        print(f"Erreur lecture pool : {e}")
        return None


def main():
    state = load_state()
    price_data = get_current_out_waaa()

    if price_data is None:
        print("RPC inaccessible, rapport horaire ignoré.")
        return

    out_waaa = price_data["out_waaa"]
    previous_rate = state.get("last_hourly_rate")

    telegram_send(f"📈 Taux (2 wUSDC → WAAA) : ~{out_waaa:,.0f} WAAA")

    if previous_rate is not None and previous_rate > 0:
        variation_percent = ((out_waaa - previous_rate) / previous_rate) * 100

        if variation_percent >= VARIATION_THRESHOLD_PERCENT:
            telegram_send(
                f"📈 Variation haussière importante : +{variation_percent:.1f}% en 1h\n"
                f"Ancien taux : ~{previous_rate:,.0f} WAAA\n"
                f"Nouveau taux : ~{out_waaa:,.0f} WAAA"
            )
        elif variation_percent <= -VARIATION_THRESHOLD_PERCENT:
            telegram_send(
                f"📉 Variation baissière importante : {variation_percent:.1f}% en 1h\n"
                f"Ancien taux : ~{previous_rate:,.0f} WAAA\n"
                f"Nouveau taux : ~{out_waaa:,.0f} WAAA"
            )

    state["last_hourly_rate"] = out_waaa
    save_state(state)


if __name__ == "__main__":
    main()