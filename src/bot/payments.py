import logging
from telegram import Update, LabeledPrice
from telegram.ext import ContextTypes, PreCheckoutQueryHandler, MessageHandler, filters
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.db.models import SubscriptionType, PaymentMethod
from src.db.repository import get_user_by_telegram_id
from src.db.session import async_session_factory
from src.services.subscription import activate_subscription

log = logging.getLogger(__name__)


def _get_prices(method: str) -> tuple[int, str, str, int]:
    if method == "monthly_card":
        return settings.monthly_price_rub, "rub", SubscriptionType.monthly.value, PaymentMethod.card.value
    elif method == "three_card":
        return settings.three_month_price_rub, "rub", SubscriptionType.three_month.value, PaymentMethod.card.value
    elif method == "monthly_stars":
        return settings.monthly_price_stars, "XTR", SubscriptionType.monthly.value, PaymentMethod.stars.value
    elif method == "three_stars":
        return settings.three_month_price_stars, "XTR", SubscriptionType.three_month.value, PaymentMethod.stars.value
    return 0, "", "", ""


async def send_card_invoice(update: Update, context: ContextTypes.DEFAULT_TYPE, sub_type: SubscriptionType) -> None:
    user = update.effective_user
    if not user:
        return

    if sub_type == SubscriptionType.monthly:
        amount = settings.monthly_price_rub
        title = "Подписка на 1 месяц"
        description = "Доступ ко всем режимам AI-тьютора на 1 месяц"
        prices = [LabeledPrice("Подписка 1 месяц", amount * 100)]
    else:
        amount = settings.three_month_price_rub
        title = "Подписка на 3 месяца"
        description = "Доступ ко всем режимам AI-тьютора на 3 месяца"
        prices = [LabeledPrice("Подписка 3 месяца", amount * 100)]

    payload = f"{sub_type.value}_card"

    await context.bot.send_invoice(
        chat_id=user.id,
        title=title,
        description=description,
        payload=payload,
        provider_token=settings.payment_provider_token,
        currency="RUB",
        prices=prices,
        need_name=False,
        need_phone=False,
        need_email=False,
        need_shipping_address=False,
        is_flexible=False,
    )


async def send_stars_invoice(update: Update, context: ContextTypes.DEFAULT_TYPE, sub_type: SubscriptionType) -> None:
    user = update.effective_user
    if not user:
        return

    if sub_type == SubscriptionType.monthly:
        amount = settings.monthly_price_stars
        title = "Подписка на 1 месяц"
        description = "Доступ ко всем режимам AI-тьютора на 1 месяц"
    else:
        amount = settings.three_month_price_stars
        title = "Подписка на 3 месяца"
        description = "Доступ ко всем режимам AI-тьютора на 3 месяца"

    payload = f"{sub_type.value}_stars"

    await context.bot.send_invoice(
        chat_id=user.id,
        title=title,
        description=description,
        payload=payload,
        provider_token="",
        currency="XTR",
        prices=[LabeledPrice(title, amount)],
    )


async def pre_checkout(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.pre_checkout_query
    if not query:
        return
    payload = query.invoice_payload
    amount = query.total_amount
    currency = query.currency

    valid = True
    if payload == "monthly_card":
        expected = settings.monthly_price_rub * 100
        valid = currency == "RUB" and amount == expected
    elif payload == "three_card":
        expected = settings.three_month_price_rub * 100
        valid = currency == "RUB" and amount == expected
    elif payload == "monthly_stars":
        valid = currency == "XTR" and amount == settings.monthly_price_stars
    elif payload == "three_stars":
        valid = currency == "XTR" and amount == settings.three_month_price_stars

    if valid:
        await query.answer(ok=True)
    else:
        await query.answer(ok=False, error_message="Ошибка платежа. Попробуйте ещё раз.")


async def successful_payment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not user:
        return
    payment = update.message.successful_payment
    if not payment:
        return

    payload = payment.invoice_payload
    telegram_charge_id = payment.telegram_payment_charge_id
    provider_charge_id = payment.provider_charge_id

    if "_card" in payload:
        sub_type_str, method_str = payload.split("_")
        payment_method = PaymentMethod.card
        currency = "RUB"
        amount = payment.total_amount / 100
    elif "_stars" in payload:
        sub_type_str, method_str = payload.split("_")
        payment_method = PaymentMethod.stars
        currency = "XTR"
        amount = payment.total_amount
    else:
        await update.message.reply_text("❌ Ошибка распознавания платежа.")
        return

    sub_type = SubscriptionType(sub_type_str)

    async with async_session_factory() as session:
        db_user = await get_user_by_telegram_id(session, user.id)
        if not db_user:
            await update.message.reply_text("❌ Пользователь не найден.")
            return
        await activate_subscription(
            session, db_user.id, sub_type, payment_method,
            amount, currency, telegram_charge_id, provider_charge_id,
        )

    await update.message.reply_text(
        "🎉 <b>Оплата прошла успешно!</b>\n\n"
        "Тебе открыт полный доступ:\n"
        "• ♾️ Безлимитные запросы\n"
        "• 🔓 Свободный режим\n"
        "• 🎯 Приоритетный доступ\n\n"
        "Задавай любой вопрос!",
        parse_mode="HTML",
    )
