import time
import os
import requests
from web3 import Web3

RPC_URL = "https://evm.moonrabbit.com"
PAIR_ADDRESS = "0x93361341D82c37437B49bc907bA0758e582D28a9"

WAAA_DECIMALS = 18
WUSDC_DECIMALS = 18

AMOUNT_IN_WUSDC = 2.0
TARGET_OUT_WAAA = 12_000_000.0
POLL_SECONDS = 20

FEE_BPS = 30

# Render Environment Variables (ne pas mettre de secret dans le code)
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

def telegram_send(msg: str) -> None:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        raise RuntimeError("TELEGRAM_BOT_TOKEN ou TELEGRAM_CHAT_ID manquant (variables d'environnement).")

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
        raise RuntimeError("Connexion RPC impossible. Vérifie RPC_URL.")

    pair = w3.eth.contract(address=Web3.to_checksum_address(PAIR_ADDRESS), abi=PAIR_ABI)

    alerted = False
    print("Surveillance… (Ctrl+C pour arrêter)")

    while True:
        r0, r1, _ = pair.functions.getReserves().call()

        # r0 = réserve WAAA (token0), r1 = réserve wUSDC (token1)
        reserve_waaa_raw = int(r0)
        reserve_wusdc_raw = int(r1)

        amount_in_raw = int(AMOUNT_IN_WUSDC * (10 ** WUSDC_DECIMALS))

        out_raw = amount_out_v2(amount_in_raw, reserve_wusdc_raw, reserve_waaa_raw, fee_bps=FEE_BPS)
        out_waaa = out_raw / (10 ** WAAA_DECIMALS)

        line = f"2 wUSDC -> ~{out_waaa:,.0f} WAAA | reserves: WAAA={reserve_waaa_raw} wUSDC={reserve_wusdc_raw}"
        print(line)

        if (out_waaa >= TARGET_OUT_WAAA) and not alerted:
            telegram_send("✅ Seuil atteint : " + line)
            alerted = True

        if out_waaa < TARGET_OUT_WAAA * 0.98:
            alerted = False

        time.sleep(POLL_SECONDS)

if __name__ == "__main__":
    main()
