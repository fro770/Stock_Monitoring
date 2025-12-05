"""
Ансамбль моделей для прогнозирования
"""

import numpy as np
from typing import Dict, List
from .base_predictor import BasePredictor
from .trend_predictor import TrendPredictor
from .finrl_predictor import FinRLPredictor
import pandas as pd
class EnsemblePredictor(BasePredictor):
    """Ансамбль предсказателей"""
    
    def __init__(self, mode: int = 2):
        """
        Args:
            mode: 1-быстрый, 2-стандартный, 3-глубокий
        """
        super().__init__("ensemble")
        self.mode = mode
        self.predictors = []
        self._init_predictors()
        
    def _init_predictors(self):
        """Инициализирует предикторы в зависимости от режима"""
        # Всегда добавляем трендовый анализатор
        self.predictors.append(TrendPredictor())
        
        if self.mode >= 2:  # Стандартный и глубокий
            self.predictors.append(FinRLPredictor())
        
        # Здесь можно добавить другие модели для глубокого режима
        
        print(f"🧠 Инициализировано {len(self.predictors)} моделей для режима {self.mode}")
    
    def predict(self, ticker: str, data: pd.DataFrame, days_ahead: int) -> Dict:
        """Прогнозирует цену с использованием ансамбля моделей"""
        if not self.predictors:
            return self._fallback_prediction(data, days_ahead)
        
        try:
            individual_predictions = []
            valid_predictions = []
            
            # Получаем прогнозы от всех моделей
            for predictor in self.predictors:
                try:
                    prediction = predictor.predict(ticker, data, days_ahead)
                    
                    if prediction and 'error' not in prediction:
                        individual_predictions.append(prediction)
                        valid_predictions.append(prediction)
                except Exception as e:
                    print(f"Ошибка в модели {predictor.name}: {e}")
            
            if not valid_predictions:
                return self._fallback_prediction(data, days_ahead)
            
            # Комбинируем прогнозы
            if len(valid_predictions) == 1:
                # Если только одна модель, возвращаем ее прогноз
                result = valid_predictions[0]
            else:
                # Взвешенное среднее по уверенности
                total_price = 0
                total_change = 0
                total_weight = 0
                
                for pred in valid_predictions:
                    weight = pred.get('confidence', 0.5)
                    total_price += pred['price'] * weight
                    total_change += pred['change_percent'] * weight
                    total_weight += weight
                
                if total_weight > 0:
                    final_price = total_price / total_weight
                    final_change = total_change / total_weight
                    
                    # Уверенность ансамбля - средняя с учетом согласованности
                    confidences = [p.get('confidence', 0.5) for p in valid_predictions]
                    changes = [p.get('change_percent', 0) for p in valid_predictions]
                    
                    avg_confidence = np.mean(confidences)
                    
                    # Проверяем согласованность
                    if len(changes) > 1:
                        std_changes = np.std(changes)
                        consistency = max(0.5, 1 - (std_changes / 10))  # Чем меньше std, тем выше согласованность
                    else:
                        consistency = 0.8
                    
                    final_confidence = avg_confidence * consistency
                    
                    result = {
                        'price': round(final_price, 2),
                        'change_percent': round(final_change, 2),
                        'confidence': round(final_confidence, 3),
                        'model': f'{self.name}_{self.mode}',
                        'models_used': [p.get('model', 'unknown') for p in valid_predictions],
                        'consistency': round(consistency, 3)
                    }
                else:
                    # Fallback если веса нулевые
                    result = valid_predictions[0]
            
            # Добавляем информацию об индивидуальных прогнозах
            if self.mode == 3:  # Только в глубоком режиме
                result['individual_predictions'] = individual_predictions
            
            return result
            
        except Exception as e:
            return self._fallback_prediction(data, days_ahead)