"""
Простой fallback модуль для прогнозирования.
Используется только если другие модели не работают.
"""

import logging
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

def predict_future_price(
    market_data_df: pd.DataFrame, 
    days_ahead: int, 
    ticker_id: int, 
    sentiment_score: float = 0.0
) -> tuple[float, float]:
    """
    Простой fallback прогноз.
    Используется только если основные модели не работают.
    """
    logger.warning(f"Используется fallback прогноз для ticker_id {ticker_id}")
    
    try:
        if market_data_df.empty or 'close_price' not in market_data_df.columns:
            raise ValueError("Нет данных о ценах")
        
        last_price = market_data_df['close_price'].iloc[-1]
        
        # Простой прогноз на основе тренда
        if len(market_data_df) >= 10:
            recent_prices = market_data_df['close_price'].tail(10).values
            x = np.arange(len(recent_prices))
            coeff = np.polyfit(x, recent_prices, 1)
            daily_trend = coeff[0] / last_price if last_price > 0 else 0.001
        else:
            daily_trend = 0.001
        
        # Добавляем влияние сентимента
        sentiment_impact = sentiment_score * 0.01  # 1% на единицу сентимента
        
        # Небольшая случайность
        random_factor = np.random.uniform(-0.003, 0.003)
        
        total_daily_change = daily_trend + sentiment_impact + random_factor
        
        predicted_price = last_price * (1 + total_daily_change * days_ahead)
        predicted_change = ((predicted_price - last_price) / last_price) * 100
        
        logger.info(f"Fallback прогноз: цена={predicted_price:.4f}, изменение={predicted_change:.2f}%")
        
        return predicted_price, predicted_change
        
    except Exception as e:
        logger.error(f"Ошибка fallback прогноза: {e}")
        # Крайний fallback
        last_price = market_data_df['close_price'].iloc[-1] if not market_data_df.empty else 100.0
        return last_price * 1.01, 1.0