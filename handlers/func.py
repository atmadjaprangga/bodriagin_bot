from datetime import datetime

def reduce_to_digit(n: int) -> int:
    """
    Сводит число к однозначному (1–9) через повторное суммирование цифр.
    Пример: 24 -> 2+4=6; 29 -> 2+9=11 -> 1+1=2.
    """
    while n > 9:
        n = sum(int(d) for d in str(n))
    return n

def calculate_numbers(date_str: str) -> tuple[int, int, int]:
    """
    Принимает дату формата DD.MM.YYYY.
    Возвращает (soul, destiny, purpose):
      soul      — сумма цифр дня (DD) → редукция;
      destiny   — сумма всех цифр (DDMMYYYY) → редукция;
      purpose   — сумма цифр дня и месяца (DDMM) → редукция.
    """
    try:
        datetime.strptime(date_str, "%d.%m.%Y")
    except ValueError:
        raise ValueError("Дата должна быть в формате DD.MM.YYYY")

    digits = [d for d in date_str if d.isdigit()]  # Все цифры
    if len(digits) != 8:
        raise ValueError("Неверная дата: ожидалось 8 цифр (DDMMYYYY).")

    day_digits = digits[0:2]      # DD
    month_digits = digits[2:4]    # MM

    soul_raw = sum(int(d) for d in day_digits)
    destiny_raw = sum(int(d) for d in digits)
    purpose_raw = sum(int(d) for d in (day_digits + month_digits))

    soul = reduce_to_digit(soul_raw)
    destiny = reduce_to_digit(destiny_raw)
    purpose = reduce_to_digit(purpose_raw)
    return soul, destiny, purpose