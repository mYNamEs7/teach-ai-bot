import os
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from sqladmin import Admin, ModelView
from sqladmin.authentication import AuthenticationBackend
from starlette.middleware.sessions import SessionMiddleware

from src.db.models import User, Subscription, Payment, ErrorLog, AdminSetting
from src.db.session import engine
from src.db.repository import (
    get_users_count, get_active_subscriptions_count, get_today_requests_count,
    get_total_revenue, get_all_users, get_all_subscriptions, get_all_payments,
    get_all_error_logs, get_user_by_telegram_id, block_user,
)
from src.db.session import async_session_factory
from src.config import settings
from src.services.notification import send_broadcast
from src.services.subscription import check_subscription
from src.admin.translations import TRANSLATIONS

SECRET_KEY = os.urandom(24).hex()


class AdminAuth(AuthenticationBackend):
    async def login(self, request: Request) -> bool:
        form = await request.form()
        username = form.get("username", "")
        password = form.get("password", "")
        if username == settings.admin_username and password == settings.admin_password:
            request.session.update({"token": SECRET_KEY})
            return True
        return False

    async def logout(self, request: Request) -> bool:
        request.session.clear()
        return True

    async def authenticate(self, request: Request) -> bool:
        token = request.session.get("token")
        return token == SECRET_KEY


class UserAdmin(ModelView, model=User):
    name = "Пользователь"
    name_plural = "Пользователи"
    icon = "fa fa-users"
    column_list = [User.id, User.telegram_id, User.username, User.first_name, User.mode, User.is_blocked, User.last_activity_at]
    column_searchable_list = [User.telegram_id, User.username]
    column_sortable_list = [User.id, User.last_activity_at]
    form_excluded_columns = [User.subscriptions, User.payments, User.last_activity_at, User.created_at]
    column_labels = {
        User.id: "ID",
        User.telegram_id: "Telegram ID",
        User.username: "Логин TG",
        User.first_name: "Имя",
        User.last_name: "Фамилия",
        User.mode: "Режим",
        User.is_blocked: "Заблокирован",
        User.created_at: "Создан",
        User.last_activity_at: "Активность",
    }


class SubscriptionAdmin(ModelView, model=Subscription):
    name = "Подписка"
    name_plural = "Подписки"
    icon = "fa fa-star"
    column_list = [Subscription.id, Subscription.user_id, Subscription.type, Subscription.payment_method, Subscription.status, Subscription.start_date, Subscription.end_date]
    column_sortable_list = [Subscription.id, Subscription.start_date, Subscription.end_date]
    column_labels = {
        Subscription.id: "ID",
        Subscription.user_id: "ID пользователя",
        Subscription.type: "Тип",
        Subscription.payment_method: "Способ оплаты",
        Subscription.status: "Статус",
        Subscription.start_date: "Начало",
        Subscription.end_date: "Окончание",
        Subscription.created_at: "Создана",
    }


class PaymentAdmin(ModelView, model=Payment):
    name = "Платёж"
    name_plural = "Платежи"
    icon = "fa fa-credit-card"
    column_list = [Payment.id, Payment.user_id, Payment.amount, Payment.currency, Payment.status, Payment.payment_method, Payment.created_at]
    column_sortable_list = [Payment.id, Payment.created_at]
    column_labels = {
        Payment.id: "ID",
        Payment.user_id: "ID пользователя",
        Payment.amount: "Сумма",
        Payment.currency: "Валюта",
        Payment.status: "Статус",
        Payment.payment_method: "Способ",
        Payment.created_at: "Дата",
    }


class ErrorLogAdmin(ModelView, model=ErrorLog):
    name = "Ошибка"
    name_plural = "Ошибки AI"
    icon = "fa fa-exclamation-triangle"
    column_list = [ErrorLog.id, ErrorLog.user_id, ErrorLog.error_type, ErrorLog.model_used, ErrorLog.created_at]
    column_sortable_list = [ErrorLog.id, ErrorLog.created_at]
    column_labels = {
        ErrorLog.id: "ID",
        ErrorLog.user_id: "ID пользователя",
        ErrorLog.error_type: "Тип ошибки",
        ErrorLog.error_message: "Сообщение",
        ErrorLog.model_used: "Модель",
        ErrorLog.created_at: "Дата",
    }


def create_admin_app() -> FastAPI:
    app = FastAPI(title="Teach AI Bot Admin", docs_url=None, redoc_url=None)
    app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY, max_age=86400)

    auth_backend = AdminAuth(secret_key=SECRET_KEY)

    # Регистрируем редирект ДО Admin, чтобы он имел приоритет
    @app.get("/admin", include_in_schema=False)
    @app.get("/admin/", include_in_schema=False)
    async def admin_redirect():
        return RedirectResponse(url="/admin/user/list")

    templates_path = os.path.join(os.path.dirname(__file__), "templates")
    admin = Admin(
        app=app,
        engine=engine,
        authentication_backend=auth_backend,
        title="Teach AI Bot Admin",
        templates_dir=templates_path,
    )

    admin.templates.env.globals["_t_ru"] = TRANSLATIONS["ru"]
    admin.templates.env.globals["_t_en"] = TRANSLATIONS["en"]

    admin.add_model_view(UserAdmin)
    admin.add_model_view(SubscriptionAdmin)
    admin.add_model_view(PaymentAdmin)
    admin.add_model_view(ErrorLogAdmin)

    @app.get("/", include_in_schema=False)
    async def root():
        return RedirectResponse(url="/admin/user/list")

    @app.get("/health", include_in_schema=False)
    async def health():
        return {"status": "ok"}

    @app.get("/api/stats")
    async def stats():
        async with async_session_factory() as session:
            users = await get_users_count(session)
            subs = await get_active_subscriptions_count(session)
            today_req = await get_today_requests_count(session)
            revenue = await get_total_revenue(session)
        return {
            "users": users,
            "active_subscriptions": subs,
            "today_requests": today_req,
            "total_revenue": revenue,
        }

    @app.post("/api/block-user/{telegram_id}")
    async def block_user_endpoint(telegram_id: int, blocked: bool = True):
        async with async_session_factory() as session:
            await block_user(session, telegram_id, blocked)
        return {"ok": True}

    @app.post("/api/broadcast")
    async def broadcast(text: str = Form(...), mode: str = Form("all")):
        sent = 0
        async with async_session_factory() as session:
            users = await get_all_users(session)
            if mode == "all":
                ids = [u.telegram_id for u in users]
            elif mode == "premium":
                ids = []
                for u in users:
                    sub = await check_subscription(session, u.telegram_id)
                    if sub:
                        ids.append(u.telegram_id)
            else:
                ids = [u.telegram_id for u in users if u.mode.value == mode]
        sent = await send_broadcast(ids, text)
        return {"sent": sent}

    return app
