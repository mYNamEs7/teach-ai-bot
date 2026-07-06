import logging
from telegram import Update
from telegram.ext import ContextTypes

from src.db.repository import get_user_by_telegram_id
from src.db.session import async_session_factory
from src.db.models import TutorMode
from src.services.rate_limiter import is_rate_limited
from src.services.subscription import check_subscription

log = logging.getLogger(__name__)


async def check_access(update: Update, context: ContextTypes.DEFAULT_TYPE) -> tuple[bool, bool, str | None]:
    user = update.effective_user
    if not user:
        return False, False, "Пользователь не идентифицирован."

    async with async_session_factory() as session:
        db_user = await get_user_by_telegram_id(session, user.id)
        if not db_user:
            return False, False, "Пользователь не найден. Напиши /start."

        if db_user.is_blocked:
            return False, False, "❌ Ваш аккаунт заблокирован. Свяжитесь с поддержкой."

        is_premium = False
        sub = await check_subscription(session, user.id)
        if sub:
            is_premium = True

        if db_user.mode == TutorMode.free and not is_premium:
            return False, is_premium, "⭐ Свободный режим доступен только по подписке.\n/subscribe"

        limited, count = await is_rate_limited(user.id, is_premium)
        if limited:
            return False, is_premium, (
                f"📊 Сегодня использовано <b>{count}</b> из {5} бесплатных запросов.\n"
                "Лимит на сегодня исчерпан. Завтра лимит обновится!\n"
                "/subscribe для безлимита ♾️"
            )

    return True, is_premium, None
