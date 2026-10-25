"""
Конфигурация системы
"""

import os
from datetime import timedelta

class Config:
    """Конфигурация приложения"""
    
    # Пути
    PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    DATA_DIR = os.path.join(PROJECT_ROOT, "data")
    REPORTS_DIR = os.path.join(PROJECT_ROOT, "reports")
    LOGS_DIR = os.path.join(PROJECT_ROOT, "logs")
    MODELS_DIR = os.path.join(PROJECT_ROOT, "models")
    
    # База данных
    DB_PATH = os.path.join(DATA_DIR, "stocks.db")
    
    # MOEX API
    MOEX_BASE_URL = "https://iss.moex.com/iss"
    MOEX_TIMEOUT = 60
    MOEX_MAX_RETRIES = 3
    
    # Параметры анализа
    DEFAULT_PREDICTION_DAYS = [1, 7, 14, 30]
    DEFAULT_HISTORY_DAYS = 720
    MIN_HISTORY_DAYS = 60
    
    # Режимы анализа
    MODES = {
        1: {"name": "Быстрый", "timeout": 20},
        2: {"name": "Стандартный", "timeout": 30},
        3: {"name": "Глубокий", "timeout": 60}
    }
    
    # Типы акций
    STOCK_TYPES = {
        1: "Все акции",
        2: "Обыкновенные акции",
        3: "Привилегированные акции"
    }
    
    # Параметры параллельной обработки
    MAX_WORKERS = 6
    TICKER_TIMEOUT = 120  # секунд на тикер
    
    @classmethod
    def ensure_directories(cls):
        """Создает необходимые директории"""
        for directory in [cls.DATA_DIR, cls.REPORTS_DIR, cls.LOGS_DIR]:
            os.makedirs(directory, exist_ok=True)