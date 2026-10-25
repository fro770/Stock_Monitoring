"""
Менеджер для работы с моделями
"""

from typing import Dict
from .ensemble import EnsemblePredictor
from ..core.config import Config

class ModelManager:
    """Менеджер моделей прогнозирования"""
    
    @staticmethod
    def get_predictor(mode: int) -> EnsemblePredictor:
        """
        Возвращает предсказатель в зависимости от режима
        
        Args:
            mode: 1-быстрый, 2-стандартный, 3-глубокий
        
        Returns:
            EnsemblePredictor с нужным набором моделей
        """
        if mode not in Config.MODES:
            mode = 2  # По умолчанию стандартный
        
        return EnsemblePredictor(mode=mode)
    
    @staticmethod
    def predict_with_retry(predictor, ticker: str, data, days_ahead: int, max_retries: int = 2) -> Dict:
        """
        Прогнозирует с возможностью повторных попыток
        
        Args:
            predictor: Объект предсказателя
            ticker: Тикер акции
            data: Исторические данные
            days_ahead: Количество дней для прогноза
            max_retries: Максимальное количество попыток
        
        Returns:
            Словарь с результатами прогноза
        """
        for attempt in range(max_retries):
            try:
                result = predictor.predict(ticker, data, days_ahead)
                
                # Проверяем валидность результата
                if result and 'price' in result and 'change_percent' in result:
                    return result
                    
            except Exception as e:
                if attempt == max_retries - 1:
                    print(f"❌ Ошибка после {max_retries} попыток для {ticker}: {e}")
        
        # Если все попытки неудачные, возвращаем fallback
        return {
            'price': data['close_price'].iloc[-1] if not data.empty else 100.0,
            'change_percent': 0.0,
            'confidence': 0.1,
            'model': 'fallback_after_retries',
            'error': 'Все попытки прогноза завершились ошибкой'
        }