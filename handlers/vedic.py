import io
import re
import logging
from datetime import datetime

from aiogram import Dispatcher
from aiogram.types import Message, InputFile, CallbackQuery
from aiogram.dispatcher.filters.state import StatesGroup, State
from aiogram.dispatcher import FSMContext

from fpdf import FPDF

logger = logging.getLogger(__name__)

# Ожидаем формат ввода: DD.MM.YYYY
VEDIC_INPUT_RE = re.compile(r"^\s*(\d{1,2})\.(\d{1,2})\.(\d{4})\s*$")

# Соответствие weekday() -> планетное число (Mon=0 .. Sun=6)
WEEKDAY_TO_PLANET = {
    0: 2,  # Monday - Луна -> 2
    1: 9,  # Tuesday - Марс -> 9
    2: 5,  # Wednesday - Меркурий -> 5
    3: 3,  # Thursday - Юпитер -> 3
    4: 6,  # Friday - Венера -> 6
    5: 8,  # Saturday - Сатурн -> 8
    6: 1,  # Sunday - Солнце -> 1
}

FONT_PATH = "fonts/DejaVuSans.ttf"  # опционально, для кириллицы

class VedicInput(StatesGroup):
    waiting = State()

def reduce_to_digit(n: int) -> int:
    if n == 0:
        return 0
    while n > 9:
        n = sum(int(d) for d in str(abs(n)))
    return n

def compute_vedic_year(day: int, month: int, target_year: int) -> dict:
    """
    Выполняет расчёт по вашей методике:
      sum = day + month + (last two digits of target_year) + planet_number_for_weekday_in_target_year
      reduced = редукция(sum)
    Возвращает подробный словарь.
    """
    try:
        dt = datetime(year=target_year, month=month, day=day)
    except ValueError as e:
        raise ValueError(f"Невалидная дата для года {target_year}: {e}")

    weekday = dt.weekday()  # 0..6 Mon..Sun
    planet_number = WEEKDAY_TO_PLANET[weekday]
    year_last_two = target_year % 100

    sum_raw = day + month + year_last_two + planet_number
    reduced = reduce_to_digit(sum_raw)

    return {
        "date_obj": dt,
        "day": day,
        "month": month,
        "year": target_year,
        "year_last_two": year_last_two,
        "weekday": weekday,
        "weekday_name": dt.strftime("%A"),
        "planet_number": planet_number,
        "sum_raw": sum_raw,
        "reduced": reduced,
    }

def build_vedic_pdf(data: dict) -> io.BytesIO:
    """
    Создаёт PDF с подробным расчётом и возвращает BytesIO.
    Файл будет отправлен под именем "Прогноз {year}.pdf".
    """
    buf = io.BytesIO()
    pdf = FPDF(orientation="L", format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    # Подключение шрифта, если доступен
    try:
        import os
        if os.path.exists(FONT_PATH):
            pdf.add_font("Main", "", FONT_PATH, uni=True)
            pdf.set_font("Main", size=14)
        else:
            pdf.set_font("Arial", size=14)
    except Exception:
        pdf.set_font("Arial", size=14)

    pdf.set_font(size=18)
    pdf.cell(0, 10, f"Ведический годовой прогноз — {data['year']}", ln=1, align="C")
    pdf.ln(4)

    pdf.set_font(size=14)
    pdf.cell(0, 8, "Исходные данные:", ln=1)
    pdf.set_font(size=12)
    pdf.cell(0, 6, f"Дата (день): {data['day']}", ln=1)
    pdf.cell(0, 6, f"Месяц: {data['month']}", ln=1)
    pdf.cell(0, 6, f"Последние две цифры года: {data['year_last_two']:02d}", ln=1)
    pdf.cell(0, 6, f"День недели в {data['year']}: {data['weekday_name']} (weekday={data['weekday']})", ln=1)
    pdf.cell(0, 6, f"Число планеты (для этого дня недели): {data['planet_number']}", ln=1)
    pdf.ln(6)

    pdf.set_font(size=14)
    pdf.cell(0, 8, "Шаги расчёта:", ln=1)
    pdf.set_font(size=12)
    expr = f"{data['day']} + {data['month']} + {data['year_last_two']} + {data['planet_number']} = {data['sum_raw']}"
    pdf.multi_cell(0, 6, expr)
    pdf.ln(4)

    sum_str = str(data['sum_raw'])
    digits = " + ".join(ch for ch in sum_str)
    digits_sum = sum(int(ch) for ch in sum_str)
    reduction_line = f"Редукция: {data['sum_raw']} -> {digits} = {digits_sum}"
    if digits_sum != data['reduced']:
        reduction_line += f" -> {data['reduced']}"
    pdf.multi_cell(0, 6, reduction_line)
    pdf.ln(6)

    pdf.set_font(size=14)
    pdf.cell(0, 8, f"Прогноз (итоговое число): {data['reduced']}", ln=1)
    pdf.ln(6)

    pdf.set_font(size=12)
    pdf.multi_cell(0, 6, "Интерпретация: (здесь можно добавить текст с описанием значения)")

    raw = pdf.output(dest="S")
    if isinstance(raw, str):
        raw = raw.encode("latin-1")
    buf.write(bytes(raw))
    buf.seek(0)
    return buf

# --- Callback handler: кнопка стартует ожидание ввода ---
async def vedic_button_handler(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await VedicInput.waiting.set()
    await callback.message.answer("Введите дату и год в формате DD.MM.YYYY\nПример: 12.05.2021")

# --- Обработка пользовательского ввода (в состоянии ожидания) ---
async def vedic_run(message: Message, state: FSMContext):
    text = message.text.strip()
    m = VEDIC_INPUT_RE.match(text)
    if not m:
        await message.answer("Неверный формат. Введите в формате DD.MM.YYYY\nНапример: 12.05.2021")
        return

    day = int(m.group(1))
    month = int(m.group(2))
    year = int(m.group(3))

    try:
        data = compute_vedic_year(day, month, year)
    except ValueError as e:
        await message.answer(f"Ошибка: {e}")
        return

    pdf_buf = build_vedic_pdf(data)
    filename = f"Прогноз {year}.pdf"
    await message.answer_document(document=InputFile(pdf_buf, filename=filename))
    await state.finish()

def register_handlers(dp: Dispatcher):
    dp.register_callback_query_handler(vedic_button_handler, lambda c: c.data == "vedic_start_button", state="*")
    dp.register_message_handler(vedic_run, state=VedicInput.waiting)