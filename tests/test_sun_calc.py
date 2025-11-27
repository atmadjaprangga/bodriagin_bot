# Небольшой тестовый скрипт для ручной проверки handlers.sun_calc
# Запустите: python tests/test_sun_calc.py  (из корня проекта)
import os
import sys
import json

# Вставляем корень проекта в sys.path — это гарантирует, что Python найдёт пакет handlers
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from handlers.sun_calc import check_birth_city_dawn

def test_example():
    info = check_birth_city_dawn("12.03.1991", "03:25", "Penza", prefer_skyfield=True, eph_path=None)
    print(json.dumps(info, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    test_example()