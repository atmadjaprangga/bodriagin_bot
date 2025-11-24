import asyncio
import logging
import os

from aiogram import Bot, Dispatcher
from aiogram.contrib.fsm_storage.memory import MemoryStorage

# Импорты ваших обработчиков
# handlers.start содержит функцию all_handlers(dp)
# handlers.vedic содержит функцию register_handlers(dp) (если вы добавили vedic.py)
from handlers.start import all_handlers
try:
    from handlers import vedic
    VEDIC_AVAILABLE = True
except Exception:
    VEDIC_AVAILABLE = False

logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")  # Лучше передавать токен через переменные окружения

async def main():
    logging.basicConfig(level=logging.INFO)
    logger.info("Bot starting..")

    storage = MemoryStorage()

    # Если токен пустой — покажем подсказку и выйдем
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN не установлен. Установите переменную окружения BOT_TOKEN или впишите токен в bot.py.")
        return

    bot = Bot(token=BOT_TOKEN, parse_mode='HTML')
    dp = Dispatcher(bot, storage=storage)

    # Регистрируем обработчики из handlers/start.py
    all_handlers(dp)

    # Регистрируем обработчики для ведического прогноза, если модуль доступен
    if VEDIC_AVAILABLE:
        try:
            vedic.register_handlers(dp)
            logger.info("Registered vedic handlers")
        except Exception:
            logger.exception("Не удалось зарегистрировать vedic handlers")

    try:
        await dp.start_polling()
    finally:
        await dp.storage.close()
        await dp.storage.wait_closed()
        await bot.session.close()

def cli():
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info('Bot stopped by User')

if __name__ == '__main__':
    cli()