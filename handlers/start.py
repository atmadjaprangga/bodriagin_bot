import os
import re
import io
import logging
import importlib

from aiogram import Dispatcher
from aiogram.types import Message, InputFile, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.dispatcher.filters.state import StatesGroup, State
from aiogram.dispatcher import FSMContext

# Попытка корректного импорта модуля handlers.func:
# используем модульный импорт, чтобы избежать проблем с относительными/абсолютными путями.
try:
    import handlers.func as func_mod
except Exception:
    try:
        # если запускается как модуль внутри пакета
        from . import func as func_mod
    except Exception:
        # финальный fallback через importlib (может поднять исключение, если модуля нет)
        func_mod = importlib.import_module("handlers.func")

# Попытка импортировать модуль со словарями текстов.
# В разных установках файл может лежать как dict.py в корне проекта или как handlers/dict.py.
# Пробуем несколько вариантов; если ни один не сработает — подставляем заглушки, чтобы бот не падал.
text_d = {}
s_text = {}
p_text = {}

DICT_LOADED = False
# варианты импорта в порядке предпочтения
for mod_name in ("handlers.dict", "dict"):
    try:
        dict_mod = importlib.import_module(mod_name)
        # ожидаем, что модуль экспортирует словари text_d, s_text, p_text
        text_d = getattr(dict_mod, "text_d", {})
        s_text = getattr(dict_mod, "s_text", {})
        p_text = getattr(dict_mod, "p_text", {})
        DICT_LOADED = True
        logging.info("Loaded dict module: %s", mod_name)
        break
    except Exception:
        continue

if not DICT_LOADED:
    # пробуем относительный импорт (если запускается как пакет)
    try:
        from . import dict as dict_mod  # type: ignore
        text_d = getattr(dict_mod, "text_d", {})
        s_text = getattr(dict_mod, "s_text", {})
        p_text = getattr(dict_mod, "p_text", {})
        DICT_LOADED = True
        logging.info("Loaded dict module via relative import")
    except Exception:
        logging.warning("Модуль dict не найден. Используются заглушки для text_d, s_text, p_text.")
        # Подставляем минимальные заглушки, чтобы код не падал. При тестировании замените на реальные тексты.
        for i in range(1, 10):
            text_d.setdefault(i, f"Описание для Числа Души {i} отсутствует.")
            s_text.setdefault(i, f"Описание для Числа Судьбы {i} отсутствует.")
            p_text.setdefault(i, f"Описание для Числа Предназначения {i} отсутствует.")

from fpdf import FPDF  # опционально, для совместимости с ранее использованным кодом

logger = logging.getLogger(__name__)

DATE_REGEX = re.compile(r"^\d{2}\.\d{2}\.\d{4}$")

class Date(StatesGroup):
    date = State()

# ---- build main menu (inline) ----
def build_main_menu() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton(text="Получить нумерологический разбор", callback_data="start_calc"),
        InlineKeyboardButton(text="Получить разбор на год", callback_data="vedic_start_button"),
        InlineKeyboardButton(text="Обо мне", callback_data="about_bot"),
    )
    return kb

# ---- /start handler: показывает меню ----
async def startbot(message: Message, state: FSMContext):
    photo_path = 'img/Logo.jpg'
    caption = (
        "Привет, я электронный помощник супер эксперта и наставника Екатерины Бодрягиной.\n\n"
        "Выберите действие в меню ниже:"
    )
    kb = build_main_menu()
    if os.path.exists(photo_path):
        try:
            photo = InputFile(photo_path)
            await message.answer_photo(photo=photo, caption=caption, reply_markup=kb)
        except Exception:
            logger.exception("Не удалось отправить фото в /start")
            await message.answer(caption, reply_markup=kb)
    else:
        await message.answer(caption, reply_markup=kb)

# ---- callback: "Обо мне" ----
async def about_callback(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    about_text = (
        "Екатерина Бодрягина — нумеролог и энергокоуч.\n\n"
        "Этот бот формирует персональные отчёты:\n"
        "- Нумерологический разбор по дате рождения\n"
        "- Ведический годовой прогноз\n\n"
        "Контакты: @your_telegram_username"
    )
    # Отвечаем в чате пользователя
    await callback.message.answer(about_text)

# ---- callback: "Получить нумерологический разбор" ----
async def start_calc_callback(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await Date.date.set()
    await callback.message.answer('Отправьте свою дату рождения в формате DD.MM.YYYY\n\nПример: 12.02.1992')

# ---- runfunc: обрабатывает ввод даты и вызывает mainfunc из handlers.func ----
async def runfunc(message: Message, state: FSMContext):
    """
    Ожидается, что func_mod.mainfunc принимает строку 'DD.MM.YYYY' и возвращает три числовых значения,
    как это было в оригинальном handlers/func.py: d, s, p = mainfunc(date_str)
    """
    text = message.text.strip()
    if len(text) == 10 and DATE_REGEX.match(text):
        try:
            # вызываем mainfunc через модуль func_mod (без прямого from ... import ...)
            d, s, p = func_mod.mainfunc(text)
            # отправляем длинные тексты постранично (как в оригинале)
            try:
                if len(text_d.get(d, "")) > 4096:
                    for x in range(0, len(text_d[d]), 4096):
                        await message.answer(text_d[d][x:x + 4096])
                else:
                    await message.answer(text_d.get(d, "Описание отсутствует."))
            except Exception:
                logger.exception("Не удалось отправить text_d for d=%s", d)
            try:
                if len(s_text.get(s, "")) > 4096:
                    for x in range(0, len(s_text[s]), 4096):
                        await message.answer(s_text[s][x:x+4096])
                else:
                    await message.answer(s_text.get(s, "Описание отсутствует."))
            except Exception:
                logger.exception("Не удалось отправить s_text for s=%s", s)
            try:
                await message.answer(p_text.get(p, "Описание отсутствует."))
            except Exception:
                logger.exception("Не удалось отправить p_text for p=%s", p)
        except Exception as e:
            logger.exception("Ошибка при вызове mainfunc: %s", e)
            await message.answer("Произошла ошибка при расчёте. Проверьте формат даты и попробуйте снова.")
        finally:
            await state.finish()
    else:
        await message.answer('Дата введена неверно! Попробуйте еще раз.\n\nПример: 12.02.1992')

# ---- регистрация обработчиков (имя all_handlers сохранено, чтобы bot.py работал) ----
def all_handlers(dp: Dispatcher):
    dp.register_message_handler(startbot, commands=['start'], state='*')
    dp.register_callback_query_handler(start_calc_callback, lambda c: c.data == "start_calc", state='*')
    dp.register_callback_query_handler(about_callback, lambda c: c.data == "about_bot", state='*')
    dp.register_message_handler(runfunc, state=Date.date)