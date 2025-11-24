# Bodriagin Bot

Телеграм-бот для нумерологического разбора даты рождения.

## Логика расчёта

Дата вводится в формате `DD.MM.YYYY`.

1. Число Души: сумма цифр дня (DD), редукция до 1–9.
2. Число Судьбы: сумма всех цифр (DDMMYYYY), редукция до 1–9.
3. Число Предназначения: сумма цифр дня и месяца (DDMM), редукция до 1–9.

Редукция: складываем цифры результата, пока число > 9.

Пример:  
Дата: 15.05.1993  
- Души: 1+5 = 6  
- Судьбы: 1+5+0+5+1+9+9+3 = 33 → 3+3 = 6  
- Предназначения: 1+5+0+5 = 11 → 1+1 = 2

## Установка

```bash
git clone https://github.com/atmadjaprangga/bodriagin_bot.git
cd bodriagin_bot
python -m venv venv
# Windows:
venv\Scripts\Activate.ps1
# Linux/macOS:
source venv/bin/activate
pip install -r requirements.txt
```

## Настройка

Создайте `.env`:
```
BOT_TOKEN=ВАШ_ТОКЕН
```

## Запуск

```bash
python bot.py
```

## Тесты

```bash
pytest -q
```

## Структура

```
bot.py
handlers/
  func.py
  start.py
texts/
  soul.py
  destiny.py
  purpose.py
tests/
  test_calculate.py
img/
  Logo.jpg
```

## TODO

- JSON/YAML хранение текстов
- aiogram v3 (Router)
- Rate limiting
- Логирование статистики
- Многоязычность