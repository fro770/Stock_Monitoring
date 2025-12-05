"""
Адаптер для использования FinRL LLM модели для прогнозирования цен
"""

import logging
import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Optional
import torch
import os
from pathlib import Path

logger = logging.getLogger(__name__)

try:
    from transformers import AutoModelForCausalLM, AutoTokenizer, pipeline
    HAS_TRANSFORMERS = True
except ImportError:
    HAS_TRANSFORMERS = False
    logger.warning("Transformers не установлен")

class FinRLPredictor:
    """Прогнозирование с использованием FinRL LLM модели"""
    
    def __init__(self, model_path: str = None):
        self.model = None
        self.tokenizer = None
        self.pipeline = None
        self.model_path = model_path or "models/Qwen3-4B-FinRL-ckpt_1K"
        
    def load_model(self) -> bool:
        """Загружает FinRL модель"""
        if not HAS_TRANSFORMERS:
            logger.error("Transformers не установлен")
            return False
            
        if not os.path.exists(self.model_path):
            logger.error(f"Модель FinRL не найдена по пути: {self.model_path}")
            return False
            
        try:
            logger.info(f"Загрузка FinRL модели из {self.model_path}...")
            
            # Загружаем токенизатор
            self.tokenizer = AutoTokenizer.from_pretrained(
                self.model_path,
                trust_remote_code=True
            )
            
            # Загружаем модель
            self.model = AutoModelForCausalLM.from_pretrained(
                self.model_path,
                torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
                device_map="auto" if torch.cuda.is_available() else None,
                trust_remote_code=True
            )
            
            # Создаем pipeline для генерации текста
            self.pipeline = pipeline(
                "text-generation",
                model=self.model,
                tokenizer=self.tokenizer,
                max_new_tokens=200,
                temperature=0.7,
                do_sample=True
            )
            
            logger.info("FinRL модель загружена успешно")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка загрузки FinRL модели: {e}")
            return False
    
    def _prepare_market_context(self, symbol: str, market_data: pd.DataFrame) -> str:
        """Подготавливает контекст рынка для LLM"""
        if market_data.empty:
            return f"Акция {symbol}. Нет исторических данных."
        
        last_price = market_data['close_price'].iloc[-1]
        first_price = market_data['close_price'].iloc[0] if len(market_data) > 0 else last_price
        
        total_change = ((last_price - first_price) / first_price * 100) if first_price > 0 else 0
        
        # Статистики
        if len(market_data) >= 5:
            recent_prices = market_data['close_price'].tail(5)
            recent_change = ((recent_prices.iloc[-1] - recent_prices.iloc[0]) / recent_prices.iloc[0] * 100)
        else:
            recent_change = total_change
        
        # Подготовка текста
        context = f"""Анализ акции {symbol}:

Исторические данные:
- Текущая цена: {last_price:.2f}
- Всего дней данных: {len(market_data)}
- Общее изменение за период: {total_change:.2f}%
- Недавнее изменение (5 дней): {recent_change:.2f}%

Технические показатели:"""
        
        # Добавляем индикаторы если есть
        indicator_cols = ['RSI_14', 'MACD_12_26_9', 'BBANDS_middle_20_2.0']
        for col in indicator_cols:
            if col in market_data.columns and not market_data[col].isna().all():
                last_value = market_data[col].iloc[-1]
                context += f"\n- {col}: {last_value:.2f}"
        
        return context
    
    def _parse_llm_response(self, response_text: str) -> Tuple[float, float]:
        """Парсит ответ LLM в числовой прогноз"""
        try:
            # Ищем паттерны в ответе
            import re
            
            # Паттерн для цены
            price_patterns = [
                r'цена.*?(\d+\.?\d*)',
                r'стоимость.*?(\d+\.?\d*)',
                r'прогноз.*?(\d+\.?\d*)'
            ]
            
            # Паттерн для изменения
            change_patterns = [
                r'изменение.*?([+-]?\d+\.?\d*)%',
                r'рост.*?([+-]?\d+\.?\d*)%',
                r'падение.*?([+-]?\d+\.?\d*)%'
            ]
            
            predicted_price = None
            predicted_change = None
            
            # Ищем цену
            for pattern in price_patterns:
                match = re.search(pattern, response_text, re.IGNORECASE)
                if match:
                    try:
                        predicted_price = float(match.group(1))
                        break
                    except:
                        continue
            
            # Ищем изменение
            for pattern in change_patterns:
                match = re.search(pattern, response_text, re.IGNORECASE)
                if match:
                    try:
                        predicted_change = float(match.group(1))
                        break
                    except:
                        continue
            
            return predicted_price, predicted_change
            
        except Exception as e:
            logger.error(f"Ошибка парсинга ответа LLM: {e}")
            return None, None
    
    def predict(self, market_data: pd.DataFrame, days_ahead: int = 7) -> Tuple[float, float]:
        """Прогнозирует цену с помощью FinRL LLM"""
        
        # Если модель не загружена, используем fallback
        if not self.model or not self.pipeline:
            logger.warning("FinRL модель не загружена, используем fallback")
            return self._fallback_prediction(market_data, days_ahead)
        
        try:
            # Подготавливаем промпт
            context = self._prepare_market_context("акции", market_data)
            
            prompt = f"""{context}

На основе этих данных, спрогнозируйте цену акции через {days_ahead} дней.
Ответ должен содержать конкретную прогнозируемую цену и процентное изменение.

Формат ответа:
Прогноз: [цена] (изменение: [изменение]%)

Прогноз:"""
            
            # Генерируем ответ
            response = self.pipeline(prompt)[0]['generated_text']
            
            # Извлекаем ответ после нашего промпта
            answer = response.split("Прогноз:")[-1].strip()
            
            logger.info(f"FinRL ответ: {answer[:100]}...")
            
            # Парсим ответ
            predicted_price, predicted_change = self._parse_llm_response(answer)
            
            if predicted_price is not None:
                return predicted_price, predicted_change or 0.0
            else:
                logger.warning("Не удалось распарсить ответ LLM, используем fallback")
                return self._fallback_prediction(market_data, days_ahead)
                
        except Exception as e:
            logger.error(f"Ошибка прогнозирования FinRL: {e}")
            return self._fallback_prediction(market_data, days_ahead)
    
    def _fallback_prediction(self, market_data: pd.DataFrame, days_ahead: int) -> Tuple[float, float]:
        """Fallback прогноз если LLM не работает"""
        try:
            if market_data.empty or len(market_data) < 2:
                return 100.0, 0.0
            
            last_price = market_data['close_price'].iloc[-1]
            
            # Простой прогноз на основе тренда
            if len(market_data) >= 10:
                recent_data = market_data.tail(10)
                prices = recent_data['close_price'].values
                
                # Линейная регрессия для тренда
                x = np.arange(len(prices))
                coeff = np.polyfit(x, prices, 1)
                daily_change = coeff[0] / last_price if last_price > 0 else 0.001
            else:
                daily_change = 0.001  # 0.1% в день по умолчанию
            
            predicted_price = last_price * (1 + daily_change * days_ahead)
            predicted_change = ((predicted_price - last_price) / last_price) * 100
            
            return predicted_price, predicted_change
            
        except Exception as e:
            logger.error(f"Ошибка fallback прогноза: {e}")
            return 100.0, 0.0

# Глобальный экземпляр
finrl_predictor = FinRLPredictor()