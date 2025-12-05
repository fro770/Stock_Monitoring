"""
Предсказатель на основе трендового анализа
"""

import pandas as pd
import numpy as np
from typing import Dict
from .base_predictor import BasePredictor

class TrendPredictor(BasePredictor):
    """Предсказатель на основе технического анализа"""
    
    def __init__(self):
        super().__init__("trend")
        
    def predict(self, ticker: str, data: pd.DataFrame, days_ahead: int) -> Dict:
        """Прогнозирует цену на основе трендового анализа"""
        try:
            if data.empty or len(data) < 30:
                return self._fallback_prediction(data, days_ahead)
            
            last_price = data['close_price'].iloc[-1]
            
            # 1. Анализ трендов разных периодов
            trends = {}
            for window in [5, 10, 20, 50]:
                if len(data) >= window:
                    trends[window] = self._calculate_trend(data, window)
            
            if not trends:
                return self._fallback_prediction(data, days_ahead)
            
            # Взвешенный тренд (больше вес у коротких периодов)
            weights = {5: 0.4, 10: 0.3, 20: 0.2, 50: 0.1}
            weighted_trend = sum(trends.get(w, 0) * weights.get(w, 0) for w in weights)
            
            # 2. Технические индикаторы
            rsi = self._calculate_rsi(data, 14)
            volatility = self._calculate_volatility(data, 30)
            
            # 3. Коррекция на RSI
            rsi_correction = 0.0
            if rsi > 70:  # Перекупленность
                rsi_correction = -0.0015
            elif rsi < 30:  # Перепроданность
                rsi_correction = 0.002
            elif 40 < rsi < 60:  # Нейтральная зона
                rsi_correction = 0.0005
            
            # 4. Коррекция на волатильность
            volatility_correction = 0.0
            if volatility > 0.05:  # Высокая волатильность
                volatility_correction = -0.0005 * (volatility / 0.05)
            elif volatility < 0.01:  # Низкая волатильность
                volatility_correction = 0.0003
            
            # 5. Итоговый прогноз
            daily_change = weighted_trend + rsi_correction + volatility_correction
            
            # Ограничиваем изменение
            daily_change = max(-0.05, min(0.05, daily_change))
            
            predicted_price = last_price * (1 + daily_change * days_ahead)
            predicted_change = ((predicted_price - last_price) / last_price) * 100
            
            # 6. Уверенность прогноза
            confidence = 0.7  # Базовая уверенность
            
            # Коррекция на количество данных
            if len(data) >= 200:
                confidence *= 1.2
            elif len(data) < 60:
                confidence *= 0.8
            
            # Коррекция на согласованность трендов
            if len(trends) > 1:
                trend_values = list(trends.values())
                trend_std = np.std(trend_values) if len(trend_values) > 1 else 0
                if trend_std < 0.001:  # Тренды согласованы
                    confidence *= 1.1
                elif trend_std > 0.005:  # Тренды противоречивы
                    confidence *= 0.9
            
            # Коррекция на волатильность
            if volatility > 0.04:
                confidence *= 0.9
            
            confidence = min(0.95, max(0.3, confidence))
            
            return {
                'price': round(predicted_price, 2),
                'change_percent': round(predicted_change, 2),
                'confidence': round(confidence, 3),
                'model': self.name,
                'indicators': {
                    'rsi': round(rsi, 2),
                    'volatility': round(volatility, 4),
                    'trend_5d': round(trends.get(5, 0), 4),
                    'trend_20d': round(trends.get(20, 0), 4)
                }
            }
            
        except Exception as e:
            return self._fallback_prediction(data, days_ahead)