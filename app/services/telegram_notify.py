"""Send Telegram message when signal or order is processed."""
import logging
import httpx
from app.config import get_settings

logger = logging.getLogger(__name__)


def send_telegram(text: str) -> bool:
    """Send message to configured Telegram chat. Returns True if sent."""
    token = get_settings().telegram_bot_token
    chat_id = get_settings().telegram_chat_id
    if not token or not chat_id:
        return False
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        r = httpx.post(url, json={"chat_id": chat_id, "text": text}, timeout=10)
        r.raise_for_status()
        return True
    except Exception as e:
        logger.warning("Telegram send failed: %s", e)
        return False


def notify_signal(symbol: str, tf: str, action: str, close_time: int) -> None:
    send_telegram(f"[TradeBot] Signal: {symbol} {tf} action={action} close_time={close_time}")


def notify_order(symbol: str, side: str, order_type: str, qty: float, price: float, order_id: str) -> None:
    send_telegram(f"[TradeBot] Order: {symbol} {side} {order_type} qty={qty} price={price} orderId={order_id}")
