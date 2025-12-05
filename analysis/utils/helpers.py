"""
Вспомогательные функции
"""

import sys
import os
from typing import List

def add_project_to_path():
    """Добавляет корень проекта в sys.path"""
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

def format_number(number: float) -> str:
    """Форматирует число"""
    if number >= 1_000_000_000:
        return f"{number/1_000_000_000:.2f} млрд"
    elif number >= 1_000_000:
        return f"{number/1_000_000:.2f} млн"
    elif number >= 1_000:
        return f"{number/1_000:.1f} тыс"
    else:
        return f"{number:.0f}"

def get_progress_bar(progress: float, width: int = 40) -> str:
    """Возвращает строку прогресс-бара"""
    filled = int(width * progress)
    bar = '█' * filled + '░' * (width - filled)
    return f"[{bar}] {progress:.1%}"