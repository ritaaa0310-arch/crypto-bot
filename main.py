import asyncio
import ccxt.async_support as ccxt
import pandas as pd
from telegram import Bot

# ================= CONFIGURATION =================
TELEGRAM_BOT_TOKEN = "8830970392:AAGnwm9UmH_8YcE_AaZjDM6ez0lQlbemh3o"
TELEGRAM_CHAT_ID = "1314277979"

# Монеты для отслеживания
SYMBOLS = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT']
TIMEFRAME = '15m'
# =================================================

exchange = ccxt.binance({
    'enableRateLimit': True,
    'options': {'defaultType': 'spot'}
})

bot = Bot(token=TELEGRAM_BOT_TOKEN)


def calculate_rsi(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Расчет индикатора RSI"""
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))


async def fetch_candles(symbol: str, timeframe: str, limit: int = 100) -> pd.DataFrame:
    """Получение свечей с Binance"""
    try:
        ohlcv = await exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df['RSI'] = calculate_rsi(df, period=14)
        return df
    except Exception as e:
        print(f"Ошибка получения данных {symbol}: {e}")
        return pd.DataFrame()


def analyze_market(df: pd.DataFrame):
    """
    Аналитический модуль: Поиск Smart Money паттернов (FVG + RSI)
    """
    if len(df) < 5:
        return None

    # Берём последние свечи
    c1 = df.iloc[-3]  # Свеча 1 (до разрыва)
    c2 = df.iloc[-2]  # Исполнительная свеча
    c3 = df.iloc[-1]  # Текущая свеча

    last_price = c3['close']
    last_rsi = c3['RSI']

    signal = None

    # 1. Бычий FVG (Бычья зона интереса для LONG)
    # Если High 1-й свечи ниже, чем Low 3-й свечи — образовался незаполненный разрыв цен
    is_bullish_fvg = c3['low'] > c1['high']
    
    # 2. Медвежий FVG (Медвежья зона интереса для SHORT)
    is_bearish_fvg = c3['high'] < c1['low']

    # --- ЛОГИКА СИГНАЛА LONG ---
    if is_bullish_fvg and last_rsi < 60:
        entry = last_price
        stop_loss = c1['low'] * 0.998  # Стоп ниже свечи паттерна (-0.2%)
        risk = entry - stop_loss
        
        tp1 = entry + (risk * 1.5)     # Риск/Прибыль 1:1.5
        tp2 = entry + (risk * 3.0)     # Риск/Прибыль 1:3.0

        signal = {
            'type': '🟢 LONG',
            'entry': entry,
            'sl': stop_loss,
            'tp1': tp1,
            'tp2': tp2,
            'rsi': last_rsi,
            'reason': 'Бычий FVG (Imbalance) + RSI Подтверждение'
        }

    # --- ЛОГИКА СИГНАЛА SHORT ---
    elif is_bearish_fvg and last_rsi > 40:
        entry = last_price
        stop_loss = c1['high'] * 1.002  # Стоп выше свечи паттерна (+0.2%)
        risk = stop_loss - entry
        
        tp1 = entry - (risk * 1.5)
        tp2 = entry - (risk * 3.0)

        signal = {
            'type': '🔴 SHORT',
            'entry': entry,
            'sl': stop_loss,
            'tp1': tp1,
            'tp2': tp2,
            'rsi': last_rsi,
            'reason': 'Медвежий FVG (Imbalance) + RSI Подтверждение'
        }

    return signal


async def send_signal_msg(symbol: str, signal: dict):
    """Форматирование и отправка торгового сигнала в Telegram"""
    msg = (
        f"🚨 **СИГНАЛ: {symbol} ({signal['type']})**\n\n"
        f"🎯 **Вход:** `{signal['entry']:.2f} USDT`\n"
        f"🛑 **Стоп-Лосс:** `{signal['sl']:.2f} USDT`\n"
        f"🥇 **Тейк 1 (1:1.5):** `{signal['tp1']:.2f} USDT`\n"
        f"🥈 **Тейк 2 (1:3.0):** `{signal['tp2']:.2f} USDT`\n\n"
        f"📊 **Анализ:** {signal['reason']}\n"
        f"📈 **RSI:** `{signal['rsi']:.1f}`"
    )
    try:
        await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=msg, parse_mode='Markdown')
        print(f"✅ Сигнал по {symbol} отправлен!")
    except Exception as e:
        print(f"Ошибка отправки: {e}")


async def main():
    print("🤖 Бот-аналитик запущен и ищет паттерны...")
    
    signals_found = 0
    for symbol in SYMBOLS:
        df = await fetch_candles(symbol, TIMEFRAME)
        if not df.empty:
            signal = analyze_market(df)
            if signal:
                await send_signal_msg(symbol, signal)
                signals_found += 1
                await asyncio.sleep(1)
                
    if signals_found == 0:
        print("🔍 Рынок проанализирован: паттернов высокого качества прямо сейчас не найдено.")
    
    await exchange.close()

if __name__ == '__main__':
    asyncio.run(main())