import pytest
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import User, Subscription, Payment, TutorMode, SubscriptionType, PaymentMethod, SubscriptionStatus, PaymentStatus
from src.db.repository import (
    get_user_by_telegram_id,
    create_user,
    update_user_mode,
    get_active_subscription,
    create_subscription,
    create_payment,
    get_users_count,
    get_active_subscriptions_count,
    get_total_revenue,
)


@pytest.mark.asyncio
async def test_create_and_get_user(session: AsyncSession):
    user = await create_user(session, telegram_id=12345, username="testuser", first_name="Test")
    assert user.id is not None
    assert user.telegram_id == 12345
    assert user.username == "testuser"

    fetched = await get_user_by_telegram_id(session, 12345)
    assert fetched is not None
    assert fetched.id == user.id


@pytest.mark.asyncio
async def test_update_user_mode(session: AsyncSession):
    user = await create_user(session, telegram_id=67890)
    assert user.mode == TutorMode.free

    await update_user_mode(session, 67890, TutorMode.programming)
    fetched = await get_user_by_telegram_id(session, 67890)
    assert fetched is not None
    assert fetched.mode == TutorMode.programming


@pytest.mark.asyncio
async def test_active_subscription(session: AsyncSession):
    user = await create_user(session, telegram_id=111)
    sub = await create_subscription(session, user.id, SubscriptionType.monthly, PaymentMethod.card, 30)
    assert sub.status == SubscriptionStatus.active

    active = await get_active_subscription(session, user.id)
    assert active is not None
    assert active.id == sub.id


@pytest.mark.asyncio
async def test_expired_subscription_not_active(session: AsyncSession):
    user = await create_user(session, telegram_id=222)
    sub = Subscription(
        user_id=user.id,
        type=SubscriptionType.monthly,
        payment_method=PaymentMethod.card,
        status=SubscriptionStatus.expired,
        start_date=datetime.now(timezone.utc) - timedelta(days=60),
        end_date=datetime.now(timezone.utc) - timedelta(days=30),
    )
    session.add(sub)
    await session.commit()

    active = await get_active_subscription(session, user.id)
    assert active is None


@pytest.mark.asyncio
async def test_create_payment(session: AsyncSession):
    user = await create_user(session, telegram_id=333)
    payment = await create_payment(
        session, user.id, 199.0, "RUB", PaymentMethod.card,
        PaymentStatus.success, "tg_charge_1", "prov_charge_1",
    )
    assert payment.id is not None
    assert payment.amount == 199.0
