from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import User, Subscription, Payment, ErrorLog, AdminSetting
from src.db.models import SubscriptionStatus, PaymentStatus, TutorMode, SubscriptionType, PaymentMethod


async def get_user_by_telegram_id(session: AsyncSession, telegram_id: int) -> Optional[User]:
    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    return result.scalar_one_or_none()


async def create_user(session: AsyncSession, telegram_id: int, username: str | None = None,
                      first_name: str | None = None, last_name: str | None = None,
                      language_code: str | None = None) -> User:
    user = User(
        telegram_id=telegram_id,
        username=username,
        first_name=first_name,
        last_name=last_name,
        language_code=language_code,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def update_user_mode(session: AsyncSession, telegram_id: int, mode: TutorMode) -> None:
    await session.execute(
        update(User).where(User.telegram_id == telegram_id).values(mode=mode, last_activity_at=func.now())
    )
    await session.commit()


async def update_user_activity(session: AsyncSession, telegram_id: int) -> None:
    await session.execute(
        update(User).where(User.telegram_id == telegram_id).values(last_activity_at=func.now())
    )
    await session.commit()


async def block_user(session: AsyncSession, telegram_id: int, blocked: bool = True) -> None:
    await session.execute(
        update(User).where(User.telegram_id == telegram_id).values(is_blocked=blocked)
    )
    await session.commit()


async def get_active_subscription(session: AsyncSession, user_id: int) -> Optional[Subscription]:
    now = datetime.now(timezone.utc)
    result = await session.execute(
        select(Subscription).where(
            Subscription.user_id == user_id,
            Subscription.status == SubscriptionStatus.active,
            Subscription.end_date > now,
        ).order_by(Subscription.end_date.desc()).limit(1)
    )
    return result.scalar_one_or_none()


async def create_subscription(session: AsyncSession, user_id: int, sub_type: SubscriptionType,
                              payment_method: PaymentMethod, duration_days: int) -> Subscription:
    now = datetime.now(timezone.utc)
    from datetime import timedelta
    sub = Subscription(
        user_id=user_id,
        type=sub_type,
        payment_method=payment_method,
        status=SubscriptionStatus.active,
        start_date=now,
        end_date=now + timedelta(days=duration_days),
    )
    session.add(sub)
    await session.commit()
    await session.refresh(sub)
    return sub


async def expire_subscription(session: AsyncSession, sub_id: int) -> None:
    await session.execute(
        update(Subscription).where(Subscription.id == sub_id).values(status=SubscriptionStatus.expired)
    )
    await session.commit()


async def create_payment(session: AsyncSession, user_id: int, amount: float, currency: str,
                         payment_method: PaymentMethod, status: PaymentStatus = PaymentStatus.success,
                         telegram_charge_id: str | None = None, provider_charge_id: str | None = None) -> Payment:
    payment = Payment(
        user_id=user_id,
        amount=amount,
        currency=currency,
        payment_method=payment_method,
        status=status,
        telegram_payment_charge_id=telegram_charge_id,
        provider_charge_id=provider_charge_id,
    )
    session.add(payment)
    await session.commit()
    await session.refresh(payment)
    return payment


async def log_error(session: AsyncSession, error_type: str, error_message: str,
                    user_id: int | None = None, model_used: str | None = None,
                    context: dict | None = None) -> None:
    log = ErrorLog(
        user_id=user_id,
        error_type=error_type,
        error_message=error_message,
        model_used=model_used,
        context=context,
    )
    session.add(log)
    await session.commit()


async def get_users_count(session: AsyncSession) -> int:
    result = await session.execute(select(func.count(User.id)))
    return result.scalar_one()


async def get_active_subscriptions_count(session: AsyncSession) -> int:
    now = datetime.now(timezone.utc)
    result = await session.execute(
        select(func.count(Subscription.id)).where(
            Subscription.status == SubscriptionStatus.active,
            Subscription.end_date > now,
        )
    )
    return result.scalar_one()


async def get_today_requests_count(session: AsyncSession) -> int:
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    result = await session.execute(
        select(func.count(ErrorLog.id)).where(ErrorLog.created_at >= today)
    )
    return result.scalar_one()


async def get_total_revenue(session: AsyncSession) -> float:
    result = await session.execute(
        select(func.coalesce(func.sum(Payment.amount), 0)).where(Payment.status == PaymentStatus.success)
    )
    return float(result.scalar_one())


async def get_setting(session: AsyncSession, key: str) -> dict | None:
    result = await session.execute(select(AdminSetting).where(AdminSetting.key == key))
    setting = result.scalar_one_or_none()
    return setting.value if setting else None


async def set_setting(session: AsyncSession, key: str, value: dict) -> None:
    result = await session.execute(select(AdminSetting).where(AdminSetting.key == key))
    setting = result.scalar_one_or_none()
    if setting:
        setting.value = value
    else:
        session.add(AdminSetting(key=key, value=value))
    await session.commit()


GOD_MODE_KEY = "god_mode"


async def is_god_user(session: AsyncSession, telegram_id: int) -> bool:
    value = await get_setting(session, GOD_MODE_KEY)
    return value is not None and telegram_id in value.get("user_ids", [])


async def toggle_god_user(session: AsyncSession, telegram_id: int, active: bool) -> None:
    value = (await get_setting(session, GOD_MODE_KEY)) or {"user_ids": []}
    user_ids = set(value.get("user_ids", []))
    if active:
        user_ids.add(telegram_id)
    else:
        user_ids.discard(telegram_id)
    value["user_ids"] = list(user_ids)
    await set_setting(session, GOD_MODE_KEY, value)


async def get_all_users(session: AsyncSession) -> List[User]:
    result = await session.execute(select(User).order_by(User.created_at.desc()))
    return list(result.scalars().all())


async def get_all_subscriptions(session: AsyncSession) -> List[Subscription]:
    result = await session.execute(select(Subscription).order_by(Subscription.created_at.desc()))
    return list(result.scalars().all())


async def get_all_payments(session: AsyncSession) -> List[Payment]:
    result = await session.execute(select(Payment).order_by(Payment.created_at.desc()))
    return list(result.scalars().all())


async def get_all_error_logs(session: AsyncSession, limit: int = 100) -> List[ErrorLog]:
    result = await session.execute(select(ErrorLog).order_by(ErrorLog.created_at.desc()).limit(limit))
    return list(result.scalars().all())
