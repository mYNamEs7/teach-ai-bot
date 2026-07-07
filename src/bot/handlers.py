import logging
from typing import Optional

from telegram import Update
from telegram.ext import Application, ContextTypes

from src.ai.client import DEFAULT_MODEL, build_messages, stream_ai_response
from src.ai.fallback import get_next_fallback_model, update_available_models
from src.bot.commands import WELCOME_TEXT
from src.bot.keyboards import error_keyboard, mode_selection_keyboard, start_keyboard, subscription_keyboard
from src.bot.middleware import check_access
from src.bot.payments import send_card_invoice, send_stars_invoice
from src.config import settings
from src.db.models import SubscriptionType, TutorMode
from src.db.repository import get_user_by_telegram_id, log_error, update_user_activity
from src.db.session import async_session_factory
from src.redis.context import add_message, get_context
from src.services.rate_limiter import get_remaining_requests
from src.utils.formatting import format_ai_response

log = logging.getLogger(__name__)

application: Optional[Application] = None


async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return
    await query.answer()
    data = query.data
    user = update.effective_user
    if not user:
        return

    if data == "show_modes":
        await query.edit_message_text(
            "🎯 <b>Выбери режим обучения:</b>",
            reply_markup=mode_selection_keyboard(),
            parse_mode="HTML",
        )
        return

    if data == "show_subscribe":
        async with async_session_factory() as session:
            from src.services.subscription import check_subscription
            sub = await check_subscription(session, user.id)
            if sub:
                days_left = (sub.end_date - sub.start_date).days
                await query.edit_message_text(
                    f"✅ <b>У тебя активна подписка!</b>\n"
                    f"Осталось дней: <b>{days_left}</b>",
                    reply_markup=start_keyboard(),
                    parse_mode="HTML",
                )
                return

        await query.edit_message_text(
            "⭐ <b>Оформи подписку</b>\n\n"
            "• 1 месяц — 199₽ или ⭐50\n"
            "• 3 месяца — 499₽ или ⭐120\n\n"
            "Выбери способ:",
            reply_markup=subscription_keyboard(),
            parse_mode="HTML",
        )
        return

    if data.startswith("mode_"):
        mode_str = data.split("_", 1)[1]
        try:
            mode = TutorMode(mode_str)
        except ValueError:
            return

        async with async_session_factory() as session:
            db_user = await get_user_by_telegram_id(session, user.id)
            if db_user:
                from src.db.repository import update_user_mode
                await update_user_mode(session, user.id, mode)
                db_user.mode = mode

        from src.redis.context import clear_context
        await clear_context(user.id)

        mode_names = {
            TutorMode.programming: "💻 Программирование",
            TutorMode.languages: "🌍 Иностранные языки",
            TutorMode.exams: "📚 Подготовка к экзаменам",
            TutorMode.free: "⭐ Свободный режим",
        }

        text = f"✅ Режим <b>«{mode_names[mode]}»</b> установлен!"
        if mode == TutorMode.free:
            async with async_session_factory() as session:
                from src.services.subscription import check_subscription
                sub = await check_subscription(session, user.id)
                if not sub:
                    text += "\n\n⚠️ <b>Свободный режим доступен только по подписке.</b>"

        await query.edit_message_text(text, reply_markup=start_keyboard(), parse_mode="HTML")
        return

    if data.startswith("sub_"):
        method = data.split("_", 1)[1]
        if method in ("monthly", "three"):
            return

        sub_type = SubscriptionType.monthly if method.startswith("monthly") else SubscriptionType.three_month
        payment_method = method.split("_")[-1]

        if payment_method == "card":
            await send_card_invoice(update, context, sub_type)
        elif payment_method == "stars":
            await send_stars_invoice(update, context, sub_type)
        return

    if data == "back_to_menu":
        async with async_session_factory() as session:
            db_user = await get_user_by_telegram_id(session, user.id)
            if db_user:
                text = f"👋 Главное меню\nТвой режим: {db_user.mode.value}"
                await query.edit_message_text(text, reply_markup=start_keyboard(), parse_mode="HTML")
            else:
                await query.edit_message_text(WELCOME_TEXT, reply_markup=start_keyboard(), parse_mode="HTML")
        return

    if data == "retry":
        await query.edit_message_text("🔄 Отправь свой вопрос заново.", reply_markup=start_keyboard())
        return

    if data == "support":
        await query.edit_message_text(
            "💬 <b>Связь с поддержкой</b>\n\n"
            f"Напишите {settings.admin_contact}\n"
            "Мы ответим в ближайшее время.",
            parse_mode="HTML",
        )
        return


async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not user or not update.message or not update.message.text:
        return

    text = update.message.text.strip()
    if not text:
        return

    allowed, is_premium, error_msg = await check_access(update, context)
    if not allowed:
        await update.message.reply_text(error_msg or "Доступ запрещён.", parse_mode="HTML")
        return

    async with async_session_factory() as session:
        db_user = await get_user_by_telegram_id(session, user.id)
        if not db_user:
            await update.message.reply_text("Напиши /start чтобы начать.")
            return
        mode = db_user.mode
        await update_user_activity(session, user.id)

    context_messages = await get_context(user.id)
    messages = build_messages(mode.value, context_messages, text)

    await update.message.reply_chat_action("typing")

    reply = await update.message.reply_text("✅ Запрос получен. Отправляю AI...", parse_mode="HTML")

    full_response = ""
    full_reasoning = ""
    current_model = DEFAULT_MODEL
    models_tried = []
    last_text = ""

    for attempt in range(3):
        try:
            if attempt > 0:
                text = f"🔄 Пробую другую модель AI... (попытка {attempt + 1})"
                if text != last_text:
                    await reply.edit_text(text)
                    last_text = text

            async for chunk in stream_ai_response(current_model, messages):
                content = chunk.get("content", "")
                reasoning = chunk.get("reasoning", "")

                if reasoning:
                    full_reasoning += reasoning
                    if not content and not full_response:
                        text = "🤔 Модель размышляет..."
                        if text != last_text:
                            await reply.edit_text(text, parse_mode="HTML")
                            last_text = text

                if content:
                    first_content = not full_response
                    if first_content and not full_reasoning:
                        text = "💬 <b>Модель отвечает...</b>"
                        if text != last_text:
                            await reply.edit_text(text, parse_mode="HTML")
                            last_text = text

                    full_response += content
                    if first_content or len(full_response) % 50 < len(content):
                        display = format_ai_response(full_response)
                        try:
                            await reply.edit_text(display[:4096], parse_mode="HTML")
                            last_text = display[:4096]
                        except Exception:
                            await reply.edit_text(full_response[:4096])
                            last_text = full_response[:4096]

            if full_response:
                remaining = -1 if is_premium else await get_remaining_requests(user.id, is_premium)
                footer = ""
                if not is_premium and remaining >= 0:
                    footer = f"\n\n📊 Осталось запросов сегодня: {remaining}/{settings.free_daily_limit}"

                display_text = full_response
                if footer:
                    if not display_text.rstrip().endswith(footer.strip()):
                        display_text += footer

                display_text = format_ai_response(display_text)

                try:
                    await reply.edit_text(display_text[:4096], parse_mode="HTML")
                except Exception:
                    await reply.edit_text(full_response[:4096])

                await add_message(user.id, "user", text)
                await add_message(user.id, "assistant", full_response)
                return

        except Exception as e:
            log.warning("AI error with model %s: %s", current_model, e)
            models_tried.append(current_model)

            next_model = await get_next_fallback_model(current_model)
            if next_model and next_model not in models_tried:
                current_model = next_model
                continue
            elif not next_model:
                log.info("No fallback models cached, probing OpenRouter...")
                fresh = await update_available_models()
                fresh_models = [m for m in fresh if m not in models_tried]
                if fresh_models:
                    current_model = fresh_models[0]
                    continue

            await reply.edit_text(
                "😔 <b>AI-модели временно недоступны.</b>\n\n"
                "Мы уже ищем новые бесплатные модели. "
                "Пожалуйста, попробуйте через несколько минут.",
                reply_markup=error_keyboard(),
                parse_mode="HTML",
            )

            async with async_session_factory() as session:
                await log_error(
                    session, "ai_fallback_exhausted",
                    f"All models failed: {models_tried}. Last error: {e}",
                    user_id=user.id,
                    model_used=str(models_tried),
                    context={"mode": mode.value},
                )
            return

    if not full_response:
        await reply.edit_text(
            "😔 Не удалось получить ответ от AI. Попробуйте ещё раз.",
            reply_markup=error_keyboard(),
            parse_mode="HTML",
        )
