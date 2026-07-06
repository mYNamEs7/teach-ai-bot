import logging
from datetime import datetime, timezone, timedelta
from typing import List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Subscription, User, SubscriptionStatus
from src.db.session import async_session_factory
from src.config import settings

log = logging.getLogger(__name__)


async def check_expiring_subscriptions() -> List[tuple[int, int]]:
    now = datetime.now(timezone.utc)
    in_24h = now + timedelta(hours=24)
    in_1h = now + timedelta(hours=1)
    result: List[tuple[int, int]] = []

    async with async_session_factory() as session:
        subs = await session.execute(
            select(Subscription).where(
                Subscription.status == SubscriptionStatus.active,
                Subscription.end_date.between(now, in_24h),
            )
        )
        for sub in subs.scalars().all():
            telegram_id = sub.user.telegram_id if sub.user else None
            if telegram_id:
                hours_left = int((sub.end_date - now).total_seconds() / 3600)
                result.append((telegram_id, hours_left))
    return result


async def send_broadcast(telegram_ids: List[int], text: str) -> int:
    sent = 0
    for tid in telegram_ids:
        try:
            from src.bot.handlers import application
            if application and application.bot:
                await application.bot.send_message(chat_id=tid, text=text)
                sent += 1
        except Exception as e:
            log.warning("Failed to send broadcast to %d: %s", tid, e)
    return sent
