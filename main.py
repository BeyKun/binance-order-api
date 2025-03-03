import requests
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from binance.um_futures import UMFutures
from binance.helpers import round_step_size
from binance.enums import *

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
    quantity: float

class LimitOrderRequest(BaseModel):
    symbol: str
    side: str
    position_side: str
    quantity: float
    price: float

class CancelOrderRequest(BaseModel):
    symbol: str
    order_id: int

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
        # usdt = get_balance()
        # leverage = 5
        # price = ticker_price(request.symbol)

        # quantity = round((usdt * leverage) / price)

        order = client.new_order(
            symbol=request.symbol,
            side=request.side,
            type=ORDER_TYPE_MARKET,
            positionSide=request.position_side,
            quantity=request.quantity
        )
        send_telegram_notification(f'{request.side} {request.symbol} Order placed successfully!')
        return {"message": f"{request.side} {request.symbol} Order placed successfully", "order": order}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/place_limit_order")
def place_liomit_order(request: LimitOrderRequest):
    """Membuka posisi order baru."""
    try:
        order = client.new_order(
            symbol=request.symbol,
            side=request.side,
            type=ORDER_TYPE_LIMIT,
            positionSide=request.position_side,
            quantity=request.quantity,
            price=get_rounded_price(request.symbol, request.price),
            timeInForce=TIME_IN_FORCE_GTC
        )
        send_telegram_notification(f'{request.side} {request.symbol} Order placed successfully!')
        return {"message": f"{request.side} {request.symbol} Order placed successfully", "order": order}
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
        send_telegram_notification(f'{request.side} {request.symbol} Order closed successfully!')
        return {"message": f"{request.side} {request.symbol} Order closed successfully", "order": order}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/ticker_price/{symbol}")
def ticker_price(symbol: str):
    """Mengambil harga ticker terbaru untuk simbol tertentu."""
    ticker = client.ticker_price(symbol=symbol)
    return {'price': get_rounded_price(symbol, float(ticker["price"]))}


@app.get("/positions/{symbol}")
def positions(symbol: str):
    positions = client.get_position_risk()
    symbol_positions = []
    for position in positions:
        if position["symbol"] == symbol:
            symbol_positions.append(position)
        
    return {"positions": symbol_positions}

@app.post("/cancel_order")
def cancel_order(request: CancelOrderRequest):
    try:
        order = client.cancel_order(symbol=request.symbol, orderId=request.order_id)
        send_telegram_notification(f"{request.symbol} Order canceled successfully!")
        return {"message": f"{request.symbol} Order canceled successfully", "order": order}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/close_last_position/{symbol}")
def close_last_position(symbol: str):
    """Menutup posisi terakhir yang terbuka untuk simbol tertentu."""
    try:
        positions = client.get_position_risk()
        last_balance = get_balance()
        for position in positions:
            if position["symbol"] == symbol and float(position["positionAmt"]) != 0:
                side = position["positionSide"]
                if side == "LONG":
                    close_order(OrderRequest(symbol=symbol, side="SELL", position_side="LONG"))
                elif side == "SHORT":
                    close_order(OrderRequest(symbol=symbol, side="BUY", position_side="SHORT"))


                new_balance = get_balance()
                pnl = round(new_balance - last_balance, 2)
                msg_pnl = f"Last position {symbol} closed successfully."
                if new_balance > last_balance:
                    msg_pnl += f"\n\n 🎉 PROFIT: {pnl}"
                else:
                    msg_pnl += f"\n\n 😭LOSS: {pnl}"
                
                send_telegram_notification(msg_pnl)
                return {"message": msg_pnl, "pnl": pnl}
        return {"message": "No position found to close."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/open_orders/{symbol}")
def positions(symbol: str):
    try:
        orders = client.get_orders(symbol=symbol)    
        return {"orders": orders}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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

def get_balance():
    try:
        balance = client.balance()
        usdt = 0

        for asset in balance:
            if asset["asset"] == "USDT":
                usdt = round(float(asset["balance"]), 2)

        return usdt
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


