import requests
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from binance.um_futures import UMFutures
from binance.helpers import round_step_size

# Konfigurasi API Binance
API_KEY='your_binance_api_key'
API_SECRET='your_binance_api_secret'
client = UMFutures(key=API_KEY, secret=API_SECRET)

# Inisialisasi FastAPI
app = FastAPI()

# Konfigurasi API Key dan Secret untuk autentikasi
VALID_API_KEY = "your_valid_api_key"
VALID_API_SECRET = "your_valid_api_secret"

TELEGRAM_TOKEN="your_telegram_bot_token"
TELEGRAM_CHAT_ID="your_telegram_chat_id"

# Model untuk permintaan API
class OrderRequest(BaseModel):
    symbol: str
    side: str
    position_side: str


# Middleware untuk autentikasi API Key dan Secret
@app.middleware("http")
async def authenticate_request(request: Request, call_next):
    api_key = request.headers.get("x-api-key")
    api_secret = request.headers.get("x-api-secret")

    if api_key != VALID_API_KEY or api_secret != VALID_API_SECRET:
        raise HTTPException(status_code=401, detail="Unauthorized: Invalid API Key or Secret")

    response = await call_next(request)
    return response


@app.post("/place_order")
def place_order(request: OrderRequest):
    """Membuka posisi order baru."""
    try:
        balance = client.balance()
        usdt = 0
        leverage = 5
        price = ticker_price(request.symbol)

        for asset in balance:
            if asset["asset"] == "USDT":
                usdt = round(float(asset["balance"]), 2)

        quantity = round((usdt * leverage) / price, 2)

        order = client.new_order(
            symbol=request.symbol,
            side=request.side,
            type="MARKET",
            positionSide=request.position_side,
            quantity=quantity
        )
        send_telegram_notification(f'{request.side} Order placed successfully!')
        return {"message": "Order placed successfully", "order": order}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/close_order")
def close_order(request: OrderRequest):
    """Menutup posisi order yang ada."""
    try:
        positions = client.get_position_risk()
        position_amt = 0

        for position in positions:
            if position["symbol"] == request.symbol and position["positionSide"] == request.position_side:
                position_amt = abs(float(position["positionAmt"]))
                break

        if position_amt == 0:
            raise HTTPException(status_code=400, detail="No open position found to close.")

        order = client.new_order(
            symbol=request.symbol,
            side=request.side,
            type="MARKET",
            positionSide=request.position_side,
            quantity=position_amt
        )
        send_telegram_notification(f'{request.side} Order closed successfully!')
        return {"message": "Order closed successfully", "order": order}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/ticker_price/{symbol}")
def ticker_price(symbol: str) -> float:
    """Mengambil harga ticker terbaru untuk simbol tertentu."""
    ticker = client.ticker_price(symbol=symbol)
    return get_rounded_price(symbol, float(ticker["price"]))


def get_tick_size(symbol: str) -> float:
    """Mengambil ukuran tick untuk simbol tertentu."""
    info = client.exchange_info()
    for symbol_info in info['symbols']:
        if symbol_info['symbol'] == symbol:
            for symbol_filter in symbol_info['filters']:
                if symbol_filter['filterType'] == 'PRICE_FILTER':
                    return float(symbol_filter['tickSize'])


def get_rounded_price(symbol: str, price: float) -> float:
    """Mengembalikan harga yang telah diatur ke ukuran tick."""
    return round_step_size(price, get_tick_size(symbol))


def send_telegram_notification(message: str):
    """Mengirim notifikasi ke Telegram (placeholder)."""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    body = {
        'chat_id': TELEGRAM_CHAT_ID,
        'text': message
    }
    requests.post(url, body)
    print(message)


@app.post("/close_last_position/{symbol}")
def close_last_position(symbol: str):
    """Menutup posisi terakhir yang terbuka untuk simbol tertentu."""
    try:
        positions = client.get_position_risk()
        for position in positions:
            if position["symbol"] == symbol and float(position["positionAmt"]) != 0:
                side = position["positionSide"]
                if side == "LONG":
                    close_order(OrderRequest(symbol=symbol, side="SELL", position_side="LONG"))
                elif side == "SHORT":
                    close_order(OrderRequest(symbol=symbol, side="BUY", position_side="SHORT"))
                return {"message": "Last position closed successfully."}
        return {"message": "No position found to close."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))