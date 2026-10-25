"""
Точка входа для запуска анализа акций MOEX
"""

import sys
import os

# Добавляем корень проекта в путь
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Запускаем проверку системы
from analysis.core.validator import DataValidator

if not DataValidator():
    print("❌ Система не готова к работе")
    sys.exit(1)

# Запускаем главный модуль
from analysis.main import main

if __name__ == "__main__":
    main()