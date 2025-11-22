import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from handlers.start import all_handlers

logger = logging.getLogger(__name__)

async def main():
    logging.basicConfig(
        level = logging.INFO
    )
    logging.error('Bot starting..')

    storage = MemoryStorage()

    bot = Bot(token = '', parse_mode='HTML')
    dp = Dispatcher(bot, storage=storage)

    all_handlers(dp)



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
        logger.error('Bot stopped by User')


if __name__ == '__main__':
    cli()
