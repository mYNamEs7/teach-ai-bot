from datetime import datetime, timezone, timedelta
import logging
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import User, Subscription, PaymentMethod, SubscriptionType
from src.db.repository import (
    get_active_subscription, create_subscription, create_payment,
    expire_subscription, get_user_by_telegram_id, update_user_mode,
)
from src.db.models import TutorMode, PaymentStatus, SubscriptionStatus

log = logging.getLogger(__name__)

SUBSCRIPTION_DURATIONS = {
    SubscriptionType.monthly: 30,
    SubscriptionType.three_month: 90,
}


async def check_subscription(session: AsyncSession, telegram_id: int) -> Optional[Subscription]:
    user = await get_user_by_telegram_id(session, telegram_id)
    if not user:
        return None
    return await get_active_subscription(session, user.id)


async def activate_subscription(
    session: AsyncSession,
    db_user_id: int,
    sub_type: SubscriptionType,
    payment_method: PaymentMethod,
    amount: float,
    currency: str,
    telegram_charge_id: str | None = None,
    provider_charge_id: str | None = None,
) -> Subscription:
    duration = SUBSCRIPTION_DURATIONS[sub_type]
    sub = await create_subscription(session, db_user_id, sub_type, payment_method, duration)
    await create_payment(
        session, db_user_id, amount, currency, payment_method,
        PaymentStatus.success, telegram_charge_id, provider_charge_id,
    )
    return sub


async def expire_old_subscriptions() -> int:
    from sqlalchemy import select, update
    from src.db.models import Subscription
    from src.db.session import async_session_factory

    now = datetime.now(timezone.utc)
    async with async_session_factory() as s:
        result = await s.execute(
            select(Subscription).where(
                Subscription.status == SubscriptionStatus.active,
                Subscription.end_date <= now,
            )
        )
        expired = list(result.scalars().all())
        for sub in expired:
            sub.status = SubscriptionStatus.expired
        await s.commit()
        return len(expired)
