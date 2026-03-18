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

LOW_THRESHOLD_10M = 10_000_000
LOW_THRESHOLD_9M = 9_000_000

LEVELS = {
    "9m": 9_000_000,
    "10m": 10_000_000,
    "11m": 11_000_000,
    "12m": 12_000_000,
}

FEE_BPS = 30
STATE_FILE = "alert_state.json"

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
        "below_10m": False,
        "below_9m": False,
        "rpc_down": False,
        "levels_triggered": {
            "9m": False,
            "10m": False,
            "11m": False,
            "12m": False,
        },
    }

    if not os.path.exists(STATE_FILE):
        return default_state

    with open(STATE_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    # on complète si une clé manque
    for key, value in default_state.items():
        if key not in data:
            data[key] = value

    if "levels_triggered" not in data:
        data["levels_triggered"] = default_state["levels_triggered"]

    for level_name, value in default_state["levels_triggered"].items():
        if level_name not in data["levels_triggered"]:
            data["levels_triggered"][level_name] = value

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
        # On évite de faire planter le workflow ; on alerte une seule fois
        if not state.get("rpc_down", False):
            telegram_send("⚠️ Moonrabbit RPC indisponible : impossible de lire la pool pour le moment.")
            state["rpc_down"] = True
            save_state(state)
        return

    # Si le RPC revient, on remet l'état à normal
    if state.get("rpc_down", False):
        telegram_send("✅ Moonrabbit RPC de nouveau disponible.")
        state["rpc_down"] = False

    out_waaa = price_data["out_waaa"]
    reserve_waaa_raw = price_data["reserve_waaa_raw"]
    reserve_wusdc_raw = price_data["reserve_wusdc_raw"]

    line = (
        f"2 wUSDC -> ~{out_waaa:,.0f} WAAA | "
        f"reserves: WAAA={reserve_waaa_raw} "
        f"wUSDC={reserve_wusdc_raw}"
    )
    print(line)

    is_below_10m = out_waaa < LOW_THRESHOLD_10M
    is_below_9m = out_waaa < LOW_THRESHOLD_9M

    if is_below_10m and not state["below_10m"]:
        telegram_send(f"⚠️ Passage sous 10M : {line}")

    if is_below_9m and not state["below_9m"]:
        telegram_send(f"⚠️ Passage sous 9M : {line}")

    for level_name, threshold in LEVELS.items():
        already_triggered = state["levels_triggered"][level_name]

        if out_waaa >= threshold and not already_triggered:
            telegram_send(f"🔔 Passage au-dessus de {threshold:,.0f} WAAA : {line}")
            state["levels_triggered"][level_name] = True

        elif out_waaa < threshold:
            state["levels_triggered"][level_name] = False

    state["below_10m"] = is_below_10m
    state["below_9m"] = is_below_9m

    save_state(state)


if __name__ == "__main__":
    main()