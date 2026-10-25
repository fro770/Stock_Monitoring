"""
Настройка логирования
"""

import logging
import os
from ..core.config import Config

def setup_logging():
    """Настраивает логирование"""
    # Создаем директорию для логов
    os.makedirs(Config.LOGS_DIR, exist_ok=True)
    
    # Формат логов
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    date_format = '%Y-%m-%d %H:%M:%S'
    
    # Настраиваем корневой логгер
    logging.basicConfig(
        level=logging.INFO,
        format=log_format,
        datefmt=date_format,
        handlers=[
            logging.FileHandler(os.path.join(Config.LOGS_DIR, "stock_analysis.log")),
            logging.StreamHandler()
        ]
    )
    
    # Устанавливаем уровень для некоторых библиотек
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('requests').setLevel(logging.WARNING)
    
    print("📝 Логирование настроено")