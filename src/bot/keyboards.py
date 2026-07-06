from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def mode_selection_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton("💻 Программирование", callback_data="mode_programming"),
            InlineKeyboardButton("🌍 Иностранные языки", callback_data="mode_languages"),
        ],
        [
            InlineKeyboardButton("📚 Подготовка к экзаменам", callback_data="mode_exams"),
            InlineKeyboardButton("⭐ Свободный режим", callback_data="mode_free"),
        ],
    ]
    return InlineKeyboardMarkup(buttons)


def subscription_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton("1 месяц — 199₽", callback_data="sub_monthly_card"),
            InlineKeyboardButton("1 месяц — ⭐50", callback_data="sub_monthly_stars"),
        ],
        [
            InlineKeyboardButton("3 месяца — 499₽ (Выгодно!)", callback_data="sub_three_card"),
            InlineKeyboardButton("3 месяца — ⭐120 (Выгодно!)", callback_data="sub_three_stars"),
        ],
    ]
    return InlineKeyboardMarkup(buttons)


def back_to_menu_keyboard() -> InlineKeyboardMarkup:
    button = [[InlineKeyboardButton("🔙 В меню", callback_data="back_to_menu")]]
    return InlineKeyboardMarkup(button)


def error_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton("🔄 Повторить", callback_data="retry"),
            InlineKeyboardButton("💬 Поддержка", callback_data="support"),
        ],
    ]
    return InlineKeyboardMarkup(buttons)


def start_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton("🎯 Выбрать режим", callback_data="show_modes")],
        [InlineKeyboardButton("⭐ Подписка", callback_data="show_subscribe")],
    ]
    return InlineKeyboardMarkup(buttons)
