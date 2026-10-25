"""
Базовый класс для предсказателей
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional
import torch

class BasePredictor:
    """Базовый класс для всех предсказателей"""
    
    def __init__(self, name: str = "base"):
        self.name = name
        self.use_gpu = torch.cuda.is_available()
        self.is_loaded = False
        
    def load_model(self):
        """Загружает модель (должен быть переопределен)"""
        self.is_loaded = True
        return True
    
    def predict(self, ticker: str, data: pd.DataFrame, days_ahead: int) -> Dict:
        """
        Прогнозирует цену (должен быть переопределен)
        
        Args:
            ticker: Тикер акции
            data: Исторические данные
            days_ahead: Количество дней для прогноза
        
        Returns:
            Словарь с результатами прогноза
        """
        raise NotImplementedError
    
    def _calculate_trend(self, data: pd.DataFrame, window: int = 20) -> float:
        """Вычисляет тренд"""
        if len(data) < window:
            return 0.0
        
        prices = data['close_price'].values[-window:]
        x = np.arange(len(prices))
        coeff = np.polyfit(x, prices, 1)
        return coeff[0] / prices[0] if prices[0] > 0 else 0.0
    
    def _calculate_volatility(self, data: pd.DataFrame, window: int = 30) -> float:
        """Вычисляет волатильность"""
        if len(data) < window:
            return 0.02
        
        returns = data['close_price'].pct_change().dropna()
        if len(returns) < 10:
            return 0.02
        
        return returns.tail(window).std()
    
    def _calculate_rsi(self, data: pd.DataFrame, period: int = 14) -> float:
        """Вычисляет RSI"""
        if len(data) < period + 1:
            return 50.0
        
        delta = data['close_price'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        
        return rsi.iloc[-1] if not pd.isna(rsi.iloc[-1]) else 50.0
    
    def _fallback_prediction(self, data: pd.DataFrame, days_ahead: int) -> Dict:
        """Fallback прогноз на основе тренда"""
        try:
            if data.empty or len(data) < 10:
                return {
                    'price': 100.0,
                    'change_percent': 0.0,
                    'confidence': 0.3,
                    'model': f'{self.name}_fallback'
                }
            
            last_price = data['close_price'].iloc[-1]
            
            # Простой тренд
            if len(data) >= 20:
                trend = self._calculate_trend(data, 20)
            else:
                trend = 0.001
            
            # Волатильность
            volatility = self._calculate_volatility(data, 30)
            
            predicted_price = last_price * (1 + trend * days_ahead)
            predicted_change = ((predicted_price - last_price) / last_price) * 100
            
            # Уверенность
            confidence = 0.5
            if len(data) > 100:
                confidence = 0.6
            if volatility < 0.03:
                confidence *= 1.1
            
            return {
                'price': round(predicted_price, 2),
                'change_percent': round(predicted_change, 2),
                'confidence': round(min(0.8, confidence), 3),
                'model': f'{self.name}_fallback'
            }
            
        except Exception as e:
            return {
                'price': 100.0,
                'change_percent': 0.0,
                'confidence': 0.1,
                'model': f'{self.name}_error',
                'error': str(e)
            }