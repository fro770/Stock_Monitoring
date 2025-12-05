"""
Ансамбль моделей для прогнозирования цен акций.
Использует FinRL LLM и анализ сентимента.
"""

import logging
import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Optional
import asyncio

logger = logging.getLogger(__name__)

class MultiModelEnsemble:
    def __init__(self):
        self.models = {}
        self.model_weights = {}
        self.sentiment_analyzer = None
        self.finrl_predictor = None
        
    async def initialize_models(self):
        """Инициализирует все доступные модели"""
        logger.info("Инициализация моделей прогнозирования...")
        
        # FinRL LLM модель
        try:
            from models.ml_models.finrl_predictor import finrl_predictor
            self.finrl_predictor = finrl_predictor
            
            if self.finrl_predictor.load_model():
                self.models['finrl'] = self.finrl_predictor.predict
                self.model_weights['finrl'] = 0.6
                logger.info("FinRL LLM модель инициализирована")
            else:
                logger.warning("FinRL модель не загрузилась, используем fallback")
                # Все равно добавляем с fallback
                self.models['finrl'] = self.finrl_predictor.predict
                self.model_weights['finrl'] = 0.3
        except Exception as e:
            logger.warning(f"FinRL модель не доступна: {e}")
            # Добавляем простую модель
            self.models['simple'] = self._simple_prediction
            self.model_weights['simple'] = 1.0
            
        # Анализ сентимента с FinBERT
        try:
            from models.sentiment.analyzer import analyze_sentiment
            self.sentiment_analyzer = analyze_sentiment
            logger.info("Анализатор сентимента FinBERT инициализирован")
        except Exception as e:
            logger.warning(f"Анализатор сентимента FinBERT не доступен: {e}")
            
        # Нормализуем веса
        total_weight = sum(self.model_weights.values())
        for model in self.model_weights:
            self.model_weights[model] /= total_weight
            
        logger.info(f"Инициализировано моделей: {len(self.models)} с весами: {self.model_weights}")
        
    def _simple_prediction(self, market_data: pd.DataFrame, days_ahead: int = 1) -> Tuple[float, float]:
        """Простая модель прогнозирования как fallback"""
        try:
            if market_data.empty:
                return 100.0, 0.0
                
            last_price = market_data['close_price'].iloc[-1]
            
            # Используем технические индикаторы если есть
            if 'RSI_14' in market_data.columns:
                rsi = market_data['RSI_14'].iloc[-1]
                # RSI > 70 -> перекупленность, может упасть
                # RSI < 30 -> перепроданность, может вырасти
                if pd.notna(rsi):
                    if rsi > 70:
                        trend = -0.001  # Небольшое падение
                    elif rsi < 30:
                        trend = 0.0015  # Небольшой рост
                    else:
                        trend = 0.0005  # Нейтральный тренд
                else:
                    trend = 0.0005
            else:
                # Простая линейная экстраполяция
                if len(market_data) >= 10:
                    recent_prices = market_data['close_price'].tail(10)
                    x = np.arange(len(recent_prices))
                    coeff = np.polyfit(x, recent_prices, 1)
                    trend = coeff[0] / last_price if last_price > 0 else 0.001
                else:
                    trend = 0.001
                    
            predicted_price = last_price * (1 + trend * days_ahead)
            predicted_change = ((predicted_price - last_price) / last_price) * 100
            
            return predicted_price, predicted_change
            
        except Exception as e:
            logger.error(f"Ошибка в простой модели: {e}")
            return 100.0, 0.0
    
    async def predict_with_ensemble(self, 
                                  symbol: str,
                                  market_data: pd.DataFrame,
                                  news_data: List[Dict] = None,
                                  days_ahead: int = 7) -> Dict:
        """Прогнозирует с использованием ансамбля моделей"""
        
        predictions = {}
        
        # Получаем прогнозы от всех моделей
        for model_name, model_func in self.models.items():
            try:
                price, change = model_func(market_data, days_ahead)
                    
                predictions[model_name] = {
                    'price': price,
                    'change_percent': change,
                    'confidence': self._calculate_model_confidence(model_name, market_data)
                }
                
                logger.info(f"Модель {model_name}: цена={price:.2f}, изменение={change:.2f}%")
                
            except Exception as e:
                logger.error(f"Ошибка в модели {model_name}: {e}")
                continue
                
        # Анализ сентимента если есть новости
        sentiment_score = 0.0
        sentiment_confidence = 0.0
        if news_data and self.sentiment_analyzer:
            sentiment_score, sentiment_confidence = await self._analyze_news_sentiment(news_data)
            
        # Если нет прогнозов от моделей, создаем простой
        if not predictions:
            price, change = self._simple_prediction(market_data, days_ahead)
            predictions['simple'] = {
                'price': price,
                'change_percent': change,
                'confidence': 0.5
            }
        
        # Комбинируем прогнозы
        final_prediction = self._combine_predictions(predictions, sentiment_score, sentiment_confidence)
        
        return {
            'symbol': symbol,
            'days_ahead': days_ahead,
            'ensemble_prediction': final_prediction,
            'individual_predictions': predictions,
            'sentiment_score': sentiment_score,
            'sentiment_confidence': sentiment_confidence,
            'models_used': list(predictions.keys()),
            'final_confidence': self._calculate_final_confidence(predictions, sentiment_score, sentiment_confidence)
        }
    
    async def _analyze_news_sentiment(self, news_data: List[Dict]) -> Tuple[float, float]:
        """Анализирует сентимент новостей"""
        try:
            texts = []
            for news in news_data:
                text = f"{news.get('title', '')} {news.get('content', '')}".strip()
                if text and len(text) > 10:
                    texts.append(text)
                    
            if texts and self.sentiment_analyzer:
                sentiment_score = self.sentiment_analyzer(texts)
                confidence = min(1.0, len(texts) * 0.2)
                return sentiment_score, confidence
                
        except Exception as e:
            logger.error(f"Ошибка анализа сентимента: {e}")
            
        return 0.0, 0.0
    
    def _calculate_model_confidence(self, model_name: str, data: pd.DataFrame) -> float:
        """Вычисляет уверенность модели"""
        base_weight = self.model_weights.get(model_name, 0.5)
        
        # Корректируем на основе качества данных
        data_quality = self._assess_data_quality(data)
        
        # Для FinRL даем больше веса если есть индикаторы
        if model_name == 'finrl':
            if self._has_technical_indicators(data):
                confidence = base_weight * 1.2 * data_quality
            else:
                confidence = base_weight * 0.8 * data_quality
        else:
            confidence = base_weight * data_quality
        
        return min(1.0, max(0.1, confidence))
    
    def _has_technical_indicators(self, data: pd.DataFrame) -> bool:
        """Проверяет наличие технических индикаторов"""
        indicator_cols = ['RSI_14', 'MACD_12_26_9', 'BBANDS_middle_20_2.0']
        return any(col in data.columns for col in indicator_cols)
    
    def _assess_data_quality(self, data: pd.DataFrame) -> float:
        """Оценивает качество данных"""
        if len(data) < 10:
            return 0.3
        elif len(data) < 30:
            return 0.6
        elif len(data) < 90:
            return 0.8
        else:
            return 1.0
    
    def _combine_predictions(self, predictions: Dict, sentiment_score: float, sentiment_confidence: float) -> Dict:
        """Комбинирует прогнозы моделей"""
        if not predictions:
            return {'price': 0, 'change_percent': 0, 'confidence': 0}
            
        # Взвешенное среднее
        total_price = 0
        total_change = 0
        total_weight = 0
        
        for model_name, pred in predictions.items():
            weight = pred['confidence']
            total_price += pred['price'] * weight
            total_change += pred['change_percent'] * weight
            total_weight += weight
            
        if total_weight == 0:
            # Среднее арифметическое
            avg_price = np.mean([p['price'] for p in predictions.values()])
            avg_change = np.mean([p['change_percent'] for p in predictions.values()])
            avg_confidence = np.mean([p['confidence'] for p in predictions.values()])
        else:
            avg_price = total_price / total_weight
            avg_change = total_change / total_weight
            avg_confidence = total_weight / len(predictions)
        
        # Коррекция сентиментом
        if sentiment_confidence > 0.3 and abs(sentiment_score) > 0.2:
            sentiment_impact = sentiment_score * 0.015  # 1.5% на единицу сентимента
            final_price = avg_price * (1 + sentiment_impact)
            final_change = avg_change + (sentiment_impact * 100)
            avg_confidence = min(1.0, avg_confidence * 1.1)  # Немного повышаем уверенность
        else:
            final_price = avg_price
            final_change = avg_change
        
        return {
            'price': round(final_price, 2),
            'change_percent': round(final_change, 2),
            'confidence': round(avg_confidence, 3)
        }
    
    def _calculate_final_confidence(self, predictions: Dict, sentiment_score: float, sentiment_confidence: float) -> float:
        """Вычисляет итоговую уверенность"""
        if not predictions:
            return 0.1
            
        # Средняя уверенность моделей
        model_confidence = np.mean([p['confidence'] for p in predictions.values()])
        
        # Корректируем на согласованность
        changes = [p['change_percent'] for p in predictions.values()]
        if len(changes) > 1:
            std_changes = np.std(changes)
            consistency = max(0.5, 1 - (std_changes / 20))  # 20% std = 0.5 consistency
        else:
            consistency = 0.7
        
        # Корректируем на сентимент
        if sentiment_confidence > 0.5:
            sentiment_effect = 1.0 + (abs(sentiment_score) * 0.1)
        else:
            sentiment_effect = 1.0
        
        final_confidence = model_confidence * consistency * sentiment_effect
        return min(1.0, max(0.1, round(final_confidence, 3)))

# Глобальный экземпляр ансамбля
ensemble_predictor = MultiModelEnsemble()