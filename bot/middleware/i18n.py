from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from bot.database.methods.read import get_user_locale
from bot.i18n import reset_current_locale, set_current_locale


class LocaleMiddleware(BaseMiddleware):
    """Set request-local locale from the current user's saved preference."""

    async def __call__(
            self,
            handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
            event: TelegramObject,
            data: dict[str, Any],
    ) -> Any:
        user = getattr(event, "from_user", None)
        if user is None and isinstance(event, (Message, CallbackQuery)):
            user = event.from_user

        locale = None
        if user:
            locale = await get_user_locale(user.id)

        token = set_current_locale(locale)
        try:
            return await handler(event, data)
        finally:
            reset_current_locale(token)
