import os
import re
import io
import logging
import importlib
import asyncio
from functools import partial
from datetime import datetime

from aiogram import Dispatcher
from aiogram.types import Message, InputFile, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.dispatcher.filters.state import StatesGroup, State
from aiogram.dispatcher import FSMContext
from aiogram.utils.exceptions import InvalidQueryID, BadRequest
from fpdf import FPDF

logger = logging.getLogger(__name__)
logger.info("handlers.start loaded")

# ---------- Импорт функции расчёта ----------
try:
    import handlers.func as func_mod
except Exception:
    try:
        from . import func as func_mod
    except Exception:
        try:
            func_mod = importlib.import_module("handlers.func")
        except Exception:
            func_mod = None
            logger.warning("Модуль handlers.func не найден; расчет чисел будет недоступен.")

# ---------- Подключаем высокоточый модуль расчёта рассвета ----------
try:
    from handlers.sun_calc import check_birth_city_dawn
except Exception:
    check_birth_city_dawn = None
    logger.info("handlers.sun_calc not available; dawn checks will be disabled.")

# ---------- Импорт текстов ----------
text_d = {}
s_text = {}
p_text = {}
birthtime_texts = {}
DICT_LOADED = False
for mod_name in ("handlers.dict", "dict", "handlers.texts", "texts"):
    try:
        dict_mod = importlib.import_module(mod_name)
        text_d = getattr(dict_mod, "text_d", {}) or text_d
        s_text = getattr(dict_mod, "s_text", {}) or s_text
        p_text = getattr(dict_mod, "p_text", {}) or p_text
        birthtime_texts = getattr(dict_mod, "birthtime_texts", {}) or birthtime_texts
        DICT_LOADED = True
        logging.info("Loaded dict module: %s", mod_name)
        break
    except Exception:
        continue
if not DICT_LOADED:
    logging.warning("Тексты нумерологии не найдены. Добавлены заглушки.")
    for i in range(1, 10):
        text_d.setdefault(i, f"Описание для Числа Души {i} отсутствует.")
        s_text.setdefault(i, f"Описание для Числа Судьбы {i} отсутствует.")
        p_text.setdefault(i, f"Описание для Числа Предназначения {i} отсутствует.")
    birthtime_texts.setdefault("after_dawn", "В момент вашего рождения уже наступил гражданский рассвет — день начался. Это влияет на энергетику рождения и приносит большую открытость к внешнему миру.")
    birthtime_texts.setdefault("before_dawn", "В момент вашего рождения ещё не наступил гражданский рассвет — ночь всё ещё присутствовала. Это усиливает внутреннюю чувствительность и интуицию.")

DATE_REGEX = re.compile(r"^\d{2}\.\d{2}\.\d{4}$")
TIME_REGEX = re.compile(r"^\s*([01]?\d|2[0-3]):([0-5]\d)\s*$")

# ---------- Пути шрифтов ----------
TIMES_PATH = os.path.join("fonts", "timesnewromanpsmt.ttf")
TIMES_BOLD_PATH = os.path.join("fonts", "timesnewromanpsmt_bold.ttf")
DEJAVU_PATH = os.path.join("fonts", "DejaVuSans.ttf")
DEJAVU_BOLD_PATH = os.path.join("fonts", "DejaVuSans-Bold.ttf")

# ---------- Футер / фон / цвета ----------
FOOTER_LEFT = "Энерго коуч, нумеролог  @katebodrjagina"
FOOTER_RIGHT_NUMERO = "Нумерологический разбор"
BACKGROUND_IMAGE_PATH_NUMERO = "img/background_numerology.jpg"
BACKGROUND_COLOR = (25, 25, 30)
TEXT_COLOR = (255, 255, 255)

# ---------- Настройки размера текста ----------
TEXT_BASE_SIZE = 14
TEXT_LINE_HEIGHT = 7.0
TITLE_SIZE = 20
SECTION_TITLE_SIZE = 16

class Date(StatesGroup):
    date = State()
    time = State()
    city = State()

def build_main_menu() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton(text="Получить нумерологический разбор", callback_data="start_calc"),
        InlineKeyboardButton(text="Получить разбор на год", callback_data="vedic_start_button"),
        InlineKeyboardButton(text="Обо мне", callback_data="about_bot"),
    )
    return kb

async def startbot(message: Message, state: FSMContext):
    photo_path = 'img/Logo.jpg'
    caption = ("Привет, я электронный помощник супер эксперта и наставника Екатерины Бодрягиной.\n\n"
               "Выберите действие в меню ниже:")
    kb = build_main_menu()
    if os.path.exists(photo_path):
        try:
            await message.answer_photo(InputFile(photo_path), caption=caption, reply_markup=kb)
        except Exception:
            logger.exception("Фото не отправлено")
            await message.answer(caption, reply_markup=kb)
    else:
        await message.answer(caption, reply_markup=kb)

async def about_callback(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.answer()
    except (InvalidQueryID, BadRequest):
        pass
    txt = ("Екатерина Бодрягина — нумеролог и энергокоуч.\n\n"
           "Бот формирует:\n"
           "• Нумерологический разбор\n"
           "• Ведический годовой прогноз\n\n"
           "Контакты: @your_telegram_username")
    await callback.message.answer(txt)

async def start_calc_callback(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.answer()
    except Exception:
        pass
    await Date.date.set()
    await callback.message.answer("Отправьте дату рождения (DD.MM.YYYY)\nПример: 12.02.1992")

async def handle_date_input(message: Message, state: FSMContext):
    date_str = message.text.strip()
    if len(date_str) == 10 and DATE_REGEX.match(date_str):
        await state.update_data(birth_date=date_str)
        await Date.time.set()
        await message.answer("Отправьте время рождения (HH:MM), например 03:25 (24-часовой формат). Если время неизвестно — введите 00:00")
    else:
        await message.answer("Неверный формат даты. Пример: 12.02.1992")

async def handle_time_input(message: Message, state: FSMContext):
    t = message.text.strip()
    m = TIME_REGEX.match(t)
    if m:
        hh = int(m.group(1)); mm = int(m.group(2))
        await state.update_data(birth_time=f"{hh:02d}:{mm:02d}")
        await Date.city.set()
        await message.answer("Укажите город рождения (например: Пенза). Если не хотите указывать город — ответьте 'неизвестно'")
    else:
        await message.answer("Неверный формат времени. Пример: 03:25")

# ---------- Обработчик ввода города (и запуск генерации) ----------
async def handle_city_input(message: Message, state: FSMContext):
    city = message.text.strip()
    await state.update_data(birth_city=city)
    data = await state.get_data()
    date_str = data.get("birth_date")
    time_str = data.get("birth_time", "00:00")
    city_str = data.get("birth_city", "")
    if not date_str:
        await message.answer("Дата не найдена в сессии. Повторите запрос.")
        await state.finish()
        return

    # Рассчитываем числовые показатели
    if func_mod is None:
        await message.answer("В проекте отсутствует модуль расчёта чисел (handlers.func).")
        await state.finish()
        return

    try:
        d, s_num, p = func_mod.calculate_numbers(date_str)
    except Exception as e:
        logger.exception("Ошибка расчёта: %s", e)
        await message.answer("Ошибка расчёта нумерологических чисел. Проверьте дату.")
        await state.finish()
        return

    # ---------- Определяем абсолютный путь к de440s.bsp, если он есть в корне проекта ----------
    # используем __file__ чтобы корректно найти корень проекта независимо от текущей рабочей директории
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    eph_default_path = os.path.join(project_root, "de440s.bsp")
    eph_path = eph_default_path if os.path.isfile(eph_default_path) else None
    logger.info("Using eph_path for Skyfield: %s", eph_path)

    # Используем handlers.sun_calc, если он доступен
    dawn_info = None
    if check_birth_city_dawn is not None and city_str.lower() != "неизвестно":
        try:
            # передаём eph_path (абсолютный путь или None)
            dawn_info = check_birth_city_dawn(date_str, time_str, city_str, prefer_skyfield=True, eph_path=eph_path)
        except Exception as e:
            logger.exception("Ошибка в check_birth_city_dawn: %s", e)
            dawn_info = {"error": str(e)}
    else:
        if check_birth_city_dawn is None:
            dawn_info = {"error": "Модуль расчёта рассвета не подключён (handlers.sun_calc)."}
        else:
            dawn_info = None

    # Генерация PDF (в отдельном потоке)
    loop = asyncio.get_running_loop()
    try:
        pdf_buf = await loop.run_in_executor(None, partial(build_numerology_pdf, date_str, d, s_num, p, dawn_info))
        filename = f"Нумерологический разбор {date_str.replace('.', '-')}.pdf"
        await message.answer_document(InputFile(pdf_buf, filename=filename))
    except Exception as e:
        logger.exception("Ошибка формирования PDF: %s", e)
        await message.answer("Не удалось сформировать PDF (проверьте наличие Times или DejaVu в fonts).")
    finally:
        await state.finish()

import re as _re
def write_formatted(pdf: FPDF, text: str, normal_family: str, bold_family: str,
                    bold_style: str, size: int, line_height: float):
    if not text:
        return
    bold_re = _re.compile(r"\*\*(.+?)\*\*")
    for raw_line in text.splitlines():
        pdf.set_text_color(*TEXT_COLOR)
        if raw_line.strip() == "":
            pdf.ln(line_height); continue
        pos = 0
        for m in bold_re.finditer(raw_line):
            before = raw_line[pos:m.start()]
            bold_chunk = m.group(1)
            if before:
                try: pdf.set_font(normal_family, '', size)
                except Exception: pdf.set_font(normal_family, size=size)
                pdf.write(line_height, before)
            try:
                pdf.set_font(bold_family, bold_style, size)
            except Exception:
                try: pdf.set_font(bold_family, '', size)
                except Exception: pdf.set_font(normal_family, '', size)
            pdf.write(line_height, bold_chunk)
            pos = m.end()
        tail = raw_line[pos:]
        if tail:
            try: pdf.set_font(normal_family, '', size)
            except Exception: pdf.set_font(normal_family, size=size)
            pdf.write(line_height, tail)
        pdf.ln(line_height)

def register_fonts(pdf: FPDF):
    times_reg = os.path.exists(TIMES_PATH)
    times_bold = os.path.exists(TIMES_BOLD_PATH)
    dejavu_reg = os.path.exists(DEJAVU_PATH)
    dejavu_bold = os.path.exists(DEJAVU_BOLD_PATH)

    try:
        if times_reg: pdf.add_font("TimesNR", "", TIMES_PATH, uni=True)
        if times_bold: pdf.add_font("TimesNR", "B", TIMES_BOLD_PATH, uni=True)
        if dejavu_reg: pdf.add_font("DejaVu", "", DEJAVU_PATH, uni=True)
        if dejavu_bold: pdf.add_font("DejaVu", "B", DEJAVU_BOLD_PATH, uni=True)
    except Exception:
        logger.exception("Ошибка регистрации шрифтов")

    if times_reg:
        normal_family = "TimesNR"; bold_family = "TimesNR"; bold_style = "B" if times_bold else ""
    elif dejavu_reg:
        normal_family = "DejaVu"; bold_family = "DejaVu"; bold_style = "B" if dejavu_bold else ""
    else:
        logger.error("Нет Unicode шрифтов. Добавьте Times или DejaVu в папку fonts.")
        normal_family = "Helvetica"; bold_family = "Helvetica"; bold_style = ""
    logger.info("Using fonts: normal=%s bold=%s style=%r", normal_family, bold_family, bold_style)
    return normal_family, bold_family, bold_style

def apply_background(pdf: FPDF, image_path: str, color: tuple):
    if image_path and os.path.exists(image_path):
        try:
            pdf.image(image_path, x=0, y=0, w=pdf.w, h=pdf.h)
            return
        except Exception:
            logger.exception("Фон не вставился, заливка цветом.")
    r, g, b = color
    pdf.set_fill_color(r, g, b)
    pdf.rect(0, 0, pdf.w, pdf.h, style="F")

class ReportPDF(FPDF):
    def __init__(self, *args, **kwargs):
        self.footer_left = kwargs.pop("footer_left", "")
        self.footer_right = kwargs.pop("footer_right", "")
        self.background_image_path = kwargs.pop("background_image_path", None)
        self.background_color = kwargs.pop("background_color", (0, 0, 0))
        self.custom_text_color = kwargs.pop("custom_text_color", (255, 255, 255))
        super().__init__(*args, **kwargs)
        self.body_font_family = None
        self.bold_family = None
        self.bold_style = ""

    def header(self):
        apply_background(self, self.background_image_path, self.background_color)
        self.set_text_color(*self.custom_text_color)

    def footer(self):
        self.set_y(-18)
        self.set_text_color(*self.custom_text_color)
        fam = self.body_font_family or "Helvetica"
        try: self.set_font(fam, '', 11)
        except Exception: self.set_font("Helvetica", '', 11)
        self.cell(0, 6, self.footer_left, 0, 0, 'L')
        y = self.get_y(); self.set_y(y); self.set_x(self.l_margin)
        try: self.set_font(fam, '', 11)
        except Exception: self.set_font("Helvetica", '', 11)
        self.cell(self.w - 2 * self.l_margin, 6, self.footer_right, 0, 0, 'R')

def build_numerology_pdf(date_str: str, d: int, s_num: int, p: int, dawn_info: dict = None) -> io.BytesIO:
    buf = io.BytesIO()
    pdf = ReportPDF(
        orientation="L", format="A4",
        footer_left=FOOTER_LEFT,
        footer_right=FOOTER_RIGHT_NUMERO,
        background_image_path=BACKGROUND_IMAGE_PATH_NUMERO,
        background_color=BACKGROUND_COLOR,
        custom_text_color=TEXT_COLOR
    )
    normal_family, bold_family, bold_style = register_fonts(pdf)
    pdf.body_font_family = normal_family
    pdf.bold_family = bold_family
    pdf.bold_style = bold_style
    pdf.set_auto_page_break(auto=True, margin=15)

    # Если есть информация о рассвете, добавляем страницу
    if dawn_info:
        pdf.add_page()
        pdf.set_text_color(*TEXT_COLOR)
        try: pdf.set_font(bold_family, bold_style, SECTION_TITLE_SIZE)
        except Exception: pdf.set_font(normal_family, '', SECTION_TITLE_SIZE)
        pdf.cell(0, 10, "Информация о рассвете в месте/время рождения", ln=1)
        pdf.ln(4)

        if "error" in dawn_info:
            notice = f"Не удалось определить рассвет для указанного города/времени: {dawn_info.get('error')}"
            write_formatted(pdf, notice, normal_family, bold_family, bold_style, size=TEXT_BASE_SIZE, line_height=TEXT_LINE_HEIGHT)
        else:
            city = dawn_info.get("city", "неизвестно")
            tz = dawn_info.get("tz")
            birth_dt = dawn_info.get("birth_dt")
            dawn_dt = dawn_info.get("dawn_dt")
            was = dawn_info.get("was_dawn", False)
            lat = dawn_info.get("lat")
            lon = dawn_info.get("lon")
            display = dawn_info.get("display_name")
            lines = []
            lines.append(f"Город (введено): {city}")
            if display:
                lines.append(f"Найдено как: {display}")
            if tz:
                lines.append(f"Часовой пояс: {tz}")
            if birth_dt:
                lines.append(f"Время рождения (локальное): {birth_dt}")
            if dawn_dt:
                lines.append(f"Гражданский рассвет (dawn): {dawn_dt}")
            if lat and lon:
                try:
                    lines.append(f"Координаты: {float(lat):.6f}, {float(lon):.6f}")
                except Exception:
                    lines.append(f"Координаты: {lat}, {lon}")
            lines.append("")
            if was:
                extra = birthtime_texts.get("after_dawn") or "В момент рождения гражданский рассвет уже наступил."
            else:
                extra = birthtime_texts.get("before_dawn") or "В момент рождения гражданский рассвет ещё не наступил."
            lines.append(extra)
            write_formatted(pdf, "\n".join(lines), normal_family, bold_family, bold_style, size=TEXT_BASE_SIZE, line_height=TEXT_LINE_HEIGHT)
        try: pdf.ln(6)
        except Exception: pass

    # Числа разбора (как ранее)
    pdf.add_page()
    pdf.set_text_color(*TEXT_COLOR)
    try: pdf.set_font(bold_family, bold_style, TITLE_SIZE)
    except Exception: pdf.set_font(normal_family, '', TITLE_SIZE)
    pdf.cell(0, 12, f"Нумерологический разбор — {date_str}", ln=1, align="C")
    pdf.ln(8)

    try: pdf.set_font(bold_family, bold_style, SECTION_TITLE_SIZE)
    except Exception: pdf.set_font(normal_family, '', SECTION_TITLE_SIZE)
    pdf.cell(0, 10, f"Число Души: {d}", ln=1)
    pdf.ln(4)
    write_formatted(pdf, text_d.get(d, "Описание отсутствует."), normal_family, bold_family, bold_style,
                    size=TEXT_BASE_SIZE, line_height=TEXT_LINE_HEIGHT)

    pdf.add_page()
    pdf.set_text_color(*TEXT_COLOR)
    try: pdf.set_font(bold_family, bold_style, SECTION_TITLE_SIZE)
    except Exception: pdf.set_font(normal_family, '', SECTION_TITLE_SIZE)
    pdf.cell(0, 10, f"Число Судьбы: {s_num}", ln=1)
    pdf.ln(4)
    write_formatted(pdf, s_text.get(s_num, "Описание отсутствует."), normal_family, bold_family, bold_style,
                    size=TEXT_BASE_SIZE, line_height=TEXT_LINE_HEIGHT)

    pdf.add_page()
    pdf.set_text_color(*TEXT_COLOR)
    try: pdf.set_font(bold_family, bold_style, SECTION_TITLE_SIZE)
    except Exception: pdf.set_font(normal_family, '', SECTION_TITLE_SIZE)
    pdf.cell(0, 10, f"Число Предназначения: {p}", ln=1)
    pdf.ln(4)
    write_formatted(pdf, p_text.get(p, "Описание отсутствует."), normal_family, bold_family, bold_style,
                    size=TEXT_BASE_SIZE, line_height=TEXT_LINE_HEIGHT)

    raw = pdf.output(dest="S")
    if isinstance(raw, str):
        raw = raw.encode("latin-1", errors="ignore")
    buf.write(raw); buf.seek(0)
    return buf

def all_handlers(dp: Dispatcher):
    dp.register_message_handler(startbot, commands=['start'], state='*')
    dp.register_callback_query_handler(start_calc_callback, lambda c: c.data == "start_calc", state='*')
    dp.register_callback_query_handler(about_callback, lambda c: c.data == "about_bot", state='*')
    dp.register_message_handler(handle_date_input, state=Date.date)
    dp.register_message_handler(handle_time_input, state=Date.time)
    dp.register_message_handler(handle_city_input, state=Date.city)

if __name__ == "__main__":
    print("Loaded handlers.start")