import logging
from datetime import datetime, timezone

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from src.db.repository import get_user_by_telegram_id, create_user, update_user_mode
from src.db.session import async_session_factory
from src.db.models import TutorMode
from src.bot.keyboards import mode_selection_keyboard, subscription_keyboard, start_keyboard
from src.redis.context import clear_context
from src.config import settings

log = logging.getLogger(__name__)

WELCOME_TEXT = (
    "👋 <b>Добро пожаловать в Teach AI Bot!</b>\n\n"
    "Я — твой персональный AI-тьютор. Помогаю с:\n"
    "• 💻 Программированием\n"
    "• 🌍 Иностранными языками\n"
    "• 📚 Подготовкой к экзаменам\n\n"
    "Выбери режим или начни обучение прямо сейчас!"
)

HELP_TEXT = (
    "📖 <b>Помощь</b>\n\n"
    "• Просто напиши вопрос — я отвечу\n"
    "• <b>/programming</b> — режим программирования\n"
    "• <b>/languages</b> — режим языков\n"
    "• <b>/exams</b> — подготовка к экзаменам\n"
    "• <b>/free</b> — свободный режим (по подписке)\n"
    "• <b>/mode</b> — сменить режим\n"
    "• <b>/subscribe</b> — управление подпиской\n"
    "• <b>/support</b> — связь с поддержкой\n"
    "• <b>/god</b> — ♾️ безлимит (тест)\n"
    "• <b>/stop_god</b> — 🔒 вернуть лимиты\n"
    "• <b>/help</b> — эта справка\n\n"
    f"📊 Бесплатно: <b>{settings.free_daily_limit} запросов</b> в день"
)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not user:
        return
    async with async_session_factory() as session:
        db_user = await get_user_by_telegram_id(session, user.id)
        if not db_user:
            db_user = await create_user(
                session,
                telegram_id=user.id,
                username=user.username,
                first_name=user.first_name,
                last_name=user.last_name,
                language_code=user.language_code,
            )
            text = WELCOME_TEXT
        else:
            mode_names = {
                TutorMode.programming: "💻 Программирование",
                TutorMode.languages: "🌍 Языки",
                TutorMode.exams: "📚 Экзамены",
                TutorMode.free: "⭐ Свободный",
            }
            text = (
                f"👋 С возвращением, {user.first_name or 'друг'}!\n\n"
                f"Текущий режим: <b>{mode_names.get(db_user.mode, 'не выбран')}</b>\n"
            )

    await update.message.reply_text(text, reply_markup=start_keyboard(), parse_mode="HTML")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(HELP_TEXT, parse_mode="HTML")


async def mode_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "🎯 <b>Выбери режим обучения:</b>",
        reply_markup=mode_selection_keyboard(),
        parse_mode="HTML",
    )


async def _set_mode(update: Update, context: ContextTypes.DEFAULT_TYPE, mode: TutorMode) -> None:
    user = update.effective_user
    if not user:
        return
    async with async_session_factory() as session:
        db_user = await get_user_by_telegram_id(session, user.id)
        if db_user:
            await update_user_mode(session, user.id, mode)
        else:
            await create_user(session, telegram_id=user.id)
            await update_user_mode(session, user.id, mode)

    await clear_context(user.id)

    mode_names = {
        TutorMode.programming: "💻 Программирование",
        TutorMode.languages: "🌍 Иностранные языки",
        TutorMode.exams: "📚 Подготовка к экзаменам",
        TutorMode.free: "⭐ Свободный режим",
    }

    extra = ""
    if mode == TutorMode.free and not await _has_subscription(user.id):
        extra = "\n\n⚠️ <b>Свободный режим доступен только по подписке.</b> Оформи /subscribe"

    await update.message.reply_text(
        f"✅ Режим <b>«{mode_names[mode]}»</b> установлен!{extra}\n\n"
        "Теперь задавай свой вопрос!",
        parse_mode="HTML",
    )


async def _has_subscription(telegram_id: int) -> bool:
    from src.services.subscription import check_subscription
    async with async_session_factory() as session:
        sub = await check_subscription(session, telegram_id)
        return sub is not None


async def programming_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _set_mode(update, context, TutorMode.programming)


async def languages_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _set_mode(update, context, TutorMode.languages)


async def exams_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _set_mode(update, context, TutorMode.exams)


async def free_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _set_mode(update, context, TutorMode.free)


async def god_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not user:
        return
    async with async_session_factory() as session:
        from src.db.repository import toggle_god_user
        await toggle_god_user(session, user.id, True)
    await update.message.reply_text(
        "👑 <b>Режим бога активирован!</b>\n\n"
        "Все лимиты сняты. Чтобы отключить — /stop_god",
        parse_mode="HTML",
    )


async def stop_god_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not user:
        return
    async with async_session_factory() as session:
        from src.db.repository import toggle_god_user
        await toggle_god_user(session, user.id, False)
    await update.message.reply_text(
        "🚫 <b>Режим бога отключён.</b>\n\n"
        "Лимиты восстановлены.",
        parse_mode="HTML",
    )


async def support_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    contact = settings.admin_contact or "@admin_username"
    await update.message.reply_text(
        f"💬 <b>Связь с поддержкой</b>\n\n"
        f"Напишите {contact}\n"
        "Мы ответим в ближайшее время.",
        parse_mode="HTML",
    )


async def subscribe_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not user:
        return
    has_sub = await _has_subscription(user.id)
    if has_sub:
        await update.message.reply_text(
            "✅ <b>У тебя уже есть активная подписка!</b>\n"
            "Наслаждайся безлимитным доступом ко всем режимам.",
            parse_mode="HTML",
        )
        return

    await update.message.reply_text(
        "⭐ <b>Оформи подписку</b>\n\n"
        f"• <b>1 месяц</b> — 199₽ или ⭐50\n"
        f"• <b>3 месяца</b> — 499₽ или ⭐120 (выгодно!)\n\n"
        f"С подпиской:\n"
        f"• 🔓 Свободный режим\n"
        f"• ♾️ Без лимита запросов\n"
        f"• 🎯 Приоритет при загрузке AI\n\n"
        "Выбери способ оплаты:",
        reply_markup=subscription_keyboard(),
        parse_mode="HTML",
    )
