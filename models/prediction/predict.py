"""
Модуль для прогнозирования цен акций с использованием ансамбля моделей
"""

import sys
import os

current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))

if project_root not in sys.path:
    sys.path.insert(0, project_root)

import logging
import asyncio
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from core.database import get_or_create_ticker_id, get_exchange_for_ticker_id
from data.stock_data_fetcher import (
    get_market_data_for_ticker, 
    ensure_market_data_for_prediction, 
    detect_exchange_by_ticker, 
    update_ticker_exchange
)

try:
    import pandas_ta as ta
    HAS_PANDAS_TA = True
except ImportError:
    HAS_PANDAS_TA = False

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("logs/predict.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Константы
DEFAULT_PREDICTION_DAYS = 7
VOLATILITY_LOOKBACK = 30

async def predict_price(
    symbol: str, 
    days_ahead: int = DEFAULT_PREDICTION_DAYS, 
    exchange_hint: Optional[str] = None
) -> Dict[str, Any]:
    """
    Основная функция прогнозирования цены.
    Использует ансамбль моделей (FinRL LLM + анализ сентимента).
    """
    logger.info(f"Запуск прогноза для {symbol} на {days_ahead} дней вперед.")
    
    try:
        # 1. Определение биржи
        if not exchange_hint or exchange_hint == 'UNKNOWN':
            exchange = detect_exchange_by_ticker(symbol)
            logger.info(f"Автоматически определена биржа для {symbol}: {exchange}")
        else:
            exchange = exchange_hint
            
        # 2. Получение или создание ticker_id
        ticker_id = await get_or_create_ticker_id(symbol, exchange=exchange)
        if not ticker_id:
            logger.error(f"Тикер {symbol} не найден и не может быть создан.")
            return {
                "error": f"Тикер {symbol} не найден.", 
                "symbol": symbol, 
                "days_ahead": days_ahead
            }

        # 3. Обновление информации о бирже в БД
        current_exchange = await get_exchange_for_ticker_id(ticker_id)
        if current_exchange == 'UNKNOWN' and exchange != 'UNKNOWN':
            await update_ticker_exchange(ticker_id, exchange)
            logger.info(f"Обновлена биржа для {symbol} с UNKNOWN на {exchange}")

        # 4. Получение рыночных данных
        required_days = max(90, days_ahead * 10)
        buffer_days = 10
        
        logger.info(f"Проверка рыночных данных для {symbol} (требуется {required_days} дней)")
        
        data_updated = await ensure_market_data_for_prediction(
            symbol, 
            exchange, 
            required_days_back=required_days, 
            buffer_days=buffer_days
        )
        
        if not data_updated:
            logger.warning(f"Не удалось обновить данные для {symbol}. Продолжаем с имеющимися данными.")
        
        # 5. Получение данных из БД
        market_data_df = await get_market_data_for_ticker(ticker_id, days_back=required_days)
        
        if market_data_df.empty:
            logger.error(f"Недостаточно рыночных данных для {symbol}")
            # Пробуем получить хоть какие-то данные
            market_data_df = await get_market_data_for_ticker(ticker_id, days_back=30)
            if market_data_df.empty:
                return {
                    "error": f"Недостаточно рыночных данных для {symbol}", 
                    "symbol": symbol, 
                    "days_ahead": days_ahead
                }
            else:
                logger.warning(f"Для {symbol} доступно только {len(market_data_df)} дней данных")
        
        # 6. Очистка данных
        numeric_cols = ['open_price', 'high_price', 'low_price', 'close_price', 'volume', 'adjusted_close_price']
        for col in numeric_cols:
            if col in market_data_df.columns:
                market_data_df[col] = pd.to_numeric(market_data_df[col], errors='coerce')
        
        key_columns = ['open_price', 'high_price', 'low_price', 'close_price']
        before_clean = len(market_data_df)
        market_data_df = market_data_df.dropna(subset=key_columns)
        after_clean = len(market_data_df)
        
        if before_clean != after_clean:
            logger.warning(f"Удалено {before_clean - after_clean} строк с NaN в ключевых колонках")
        
        if market_data_df.empty:
            logger.error(f"После очистки недостаточно данных для {symbol}")
            return {
                "error": f"Недостаточно чистых данных для {symbol}", 
                "symbol": symbol, 
                "days_ahead": days_ahead
            }
        
        # 7. Вычисление технических индикаторов
        if HAS_PANDAS_TA:
            try:
                logger.info(f"Вычисление технических индикаторов для {symbol}...")
                
                # Используем только основные индикаторы
                if 'close_price' in market_data_df.columns:
                    close_series = market_data_df['close_price']
                    
                    # RSI
                    market_data_df['RSI_14'] = ta.rsi(close_series, length=14)
                    
                    # MACD
                    macd = ta.macd(close_series, fast=12, slow=26, signal=9)
                    if macd is not None:
                        for col in macd.columns:
                            market_data_df[f'MACD_{col}'] = macd[col]
                    
                    # Bollinger Bands
                    bb = ta.bbands(close_series, length=20, std=2)
                    if bb is not None:
                        for col in bb.columns:
                            market_data_df[f'BB_{col}'] = bb[col]
                    
                    # ATR
                    if all(col in market_data_df.columns for col in ['high_price', 'low_price', 'close_price']):
                        atr = ta.atr(
                            market_data_df['high_price'],
                            market_data_df['low_price'],
                            market_data_df['close_price'],
                            length=14
                        )
                        if atr is not None:
                            market_data_df['ATR_14'] = atr
                
                # Заполнение NaN в индикаторах
                indicator_cols = [col for col in market_data_df.columns if col not in numeric_cols + ['date', 'time']]
                for col in indicator_cols:
                    if market_data_df[col].isna().any():
                        market_data_df[col] = market_data_df[col].fillna(method='ffill').fillna(method='bfill').fillna(0)
                
                logger.info(f"Вычислены индикаторы: {len(indicator_cols)}")
                
            except Exception as e:
                logger.error(f"Ошибка вычисления индикаторов для {symbol}: {e}")
                logger.warning(f"Продолжаем без индикаторов")
        else:
            logger.warning("pandas-ta не установлен. Продолжаем без индикаторов.")
        
        # 8. Получение новостей для анализа сентимента
        news_list = []
        try:
            from data.news_fetcher import get_news_for_ticker
            news_list = await get_news_for_ticker(ticker_id, limit=20, days_back=3)
            logger.info(f"Получено {len(news_list)} новостей для {symbol}")
        except ImportError as e:
            logger.warning(f"Модуль news_fetcher не найден: {e}")
        except Exception as e:
            logger.warning(f"Ошибка получения новостей для {symbol}: {e}")
        
        # 9. Использование ансамбля моделей для прогнозирования
        try:
            from models.prediction.ensemble import ensemble_predictor
            
            # Инициализация моделей если нужно
            if not ensemble_predictor.models:
                await ensemble_predictor.initialize_models()
            
            # Получение прогноза от ансамбля
            ensemble_result = await ensemble_predictor.predict_with_ensemble(
                symbol=symbol,
                market_data=market_data_df,
                news_data=news_list,
                days_ahead=days_ahead
            )
            
            # Проверяем наличие ошибок
            if "error" in ensemble_result:
                logger.error(f"Ошибка ансамбля: {ensemble_result['error']}")
                raise Exception(f"Ошибка ансамбля: {ensemble_result['error']}")
            
            ensemble_pred = ensemble_result['ensemble_prediction']
            
            # 10. Расчет волатильности
            volatility = 0.0
            if len(market_data_df) >= VOLATILITY_LOOKBACK:
                recent_returns = market_data_df['close_price'].tail(VOLATILITY_LOOKBACK).pct_change().dropna()
                if len(recent_returns) > 0:
                    volatility = recent_returns.std()
                    if pd.notna(volatility):
                        volatility = float(volatility)
            
            # 11. Формирование результата
            prediction_date = datetime.now().date() + timedelta(days=days_ahead)
            
            result = {
                "symbol": symbol,
                "days_ahead": days_ahead,
                "prediction_date": prediction_date.strftime('%Y-%m-%d'),
                "predicted_price": ensemble_pred['price'],
                "predicted_change_percent": ensemble_pred['change_percent'],
                "confidence_percent": round(ensemble_pred['confidence'] * 100, 2),
                "volatility": round(volatility, 4) if volatility else 0.0,
                "sentiment_score": round(ensemble_result['sentiment_score'], 4),
                "exchange": exchange,
                "model_type": "ensemble",
                "models_used": ensemble_result.get('models_used', []),
                "sentiment_confidence": round(ensemble_result.get('sentiment_confidence', 0.0), 2)
            }
            
            logger.info(f"Прогноз для {symbol} завершен: цена={result['predicted_price']}, изменение={result['predicted_change_percent']}%, уверенность={result['confidence_percent']}%")
            return result
            
        except ImportError as e:
            logger.error(f"Ошибка импорта ансамбля: {e}")
            # Fallback на простой прогноз
            return await _simple_fallback_prediction(symbol, market_data_df, days_ahead, exchange)
            
        except Exception as e:
            logger.error(f"Ошибка ансамбля моделей: {e}")
            # Fallback на простой прогноз
            return await _simple_fallback_prediction(symbol, market_data_df, days_ahead, exchange)
        
    except Exception as e:
        logger.error(f"Критическая ошибка при прогнозировании для {symbol}: {e}", exc_info=True)
        return {
            "error": f"Внутренняя ошибка: {str(e)}", 
            "symbol": symbol, 
            "days_ahead": days_ahead
        }

async def _simple_fallback_prediction(
    symbol: str, 
    market_data: pd.DataFrame, 
    days_ahead: int, 
    exchange: str
) -> Dict[str, Any]:
    """Простой fallback прогноз если ансамбль не работает"""
    try:
        if market_data.empty or len(market_data) < 2:
            logger.warning("Недостаточно данных для fallback прогноза")
            return {
                "symbol": symbol,
                "days_ahead": days_ahead,
                "predicted_price": 100.0,
                "predicted_change_percent": 0.0,
                "confidence_percent": 10.0,
                "error": "Недостаточно данных"
            }
        
        last_price = market_data['close_price'].iloc[-1]
        
        # Простой тренд на основе последних 10 дней
        if len(market_data) >= 10:
            recent_prices = market_data['close_price'].tail(10).values
            x = np.arange(len(recent_prices))
            coeff = np.polyfit(x, recent_prices, 1)
            daily_change = coeff[0] / last_price if last_price > 0 else 0.001
        else:
            daily_change = 0.001
        
        # Небольшая случайная составляющая
        random_factor = np.random.uniform(-0.005, 0.005)
        daily_change += random_factor
        
        predicted_price = last_price * (1 + daily_change * days_ahead)
        predicted_change = ((predicted_price - last_price) / last_price) * 100
        
        prediction_date = datetime.now().date() + timedelta(days=days_ahead)
        
        return {
            "symbol": symbol,
            "days_ahead": days_ahead,
            "prediction_date": prediction_date.strftime('%Y-%m-%d'),
            "predicted_price": round(predicted_price, 2),
            "predicted_change_percent": round(predicted_change, 2),
            "confidence_percent": 30.0,  # Низкая уверенность для fallback
            "volatility": 0.02,
            "sentiment_score": 0.0,
            "exchange": exchange,
            "model_type": "simple_fallback",
            "models_used": ["simple_trend"],
            "note": "Использован простой прогноз (ансамбль не доступен)"
        }
        
    except Exception as e:
        logger.error(f"Ошибка в fallback прогнозе: {e}")
        return {
            "symbol": symbol,
            "days_ahead": days_ahead,
            "error": f"Fallback ошибка: {str(e)}"
        }

def format_prediction_output(prediction_result: Dict[str, Any]) -> str:
    """Форматирует результат прогноза для вывода в боте"""
    
    if "error" in prediction_result:
        symbol = prediction_result.get('symbol', 'UNKNOWN')
        error_msg = prediction_result['error']
        
        error_messages = {
            "недостаточно данных": f"❌ **Недостаточно данных для {symbol}**\n\nПопробуйте другой тикер или подождите обновления данных.",
            "тикер не найден": f"❌ **Тикер {symbol} не найден**\n\nПроверьте правильность написания.",
            "внутренняя ошибка": f"❌ **Внутренняя ошибка для {symbol}**\n\nПопробуйте позже."
        }
        
        for key, msg in error_messages.items():
            if key in error_msg.lower():
                return msg
        
        return f"❌ **Ошибка прогноза для {symbol}:**\n{error_msg}"
    
    try:
        symbol = prediction_result["symbol"]
        days = prediction_result["days_ahead"]
        date_str = prediction_result["prediction_date"]
        price = prediction_result["predicted_price"]
        change = prediction_result["predicted_change_percent"]
        confidence = prediction_result["confidence_percent"]
        sentiment = prediction_result.get("sentiment_score", 0)
        exchange = prediction_result.get("exchange", "Unknown")
        model_type = prediction_result.get("model_type", "ensemble")
        
        change_sign = "+" if change >= 0 else ""
        change_emoji = "📈" if change >= 0 else "📉"
        
        # Эмодзи для уверенности
        if confidence >= 70:
            confidence_emoji = "🟢"
        elif confidence >= 50:
            confidence_emoji = "🟡"
        else:
            confidence_emoji = "🔴"
        
        # Эмодзи для биржи
        if exchange == "MOEX":
            exchange_emoji = "🇷🇺"
        elif exchange in ["NASDAQ", "NYSE"]:
            exchange_emoji = "🇺🇸"
        else:
            exchange_emoji = "💱"
        
        # Эмодзи для модели
        if model_type == "ensemble":
            model_emoji = "🧠"
        else:
            model_emoji = "⚡"
        
        result_lines = [
            f"{change_emoji} **Прогноз для {symbol}** {exchange_emoji}",
            f"📅 Через {days} дней ({date_str}):",
            f"💰 **Цена:** {price:.2f} ({change_sign}{change:.2f}%)",
            f"🎯 **Уверенность:** {confidence_emoji} {confidence:.1f}%",
        ]
        
        # Информация о модели
        if model_type != "ensemble":
            result_lines.append(f"⚙️ **Модель:** {model_emoji} {model_type}")
        
        # Сентимент
        if abs(sentiment) > 0.1:
            sentiment_emoji = "😊" if sentiment > 0 else "😟"
            result_lines.append(f"📰 **Сентимент:** {sentiment_emoji} {sentiment:.3f}")
        
        # Биржа
        result_lines.append(f"🏛️ **Биржа:** {exchange}")
        
        # Дополнительная информация если есть
        if "note" in prediction_result:
            result_lines.append(f"\n💡 {prediction_result['note']}")
        
        return "\n".join(result_lines)
        
    except KeyError as e:
        logger.error(f"Ключ отсутствует в результате прогноза: {e}")
        return f"❌ **Ошибка форматирования:** ключ {e} не найден."
    except Exception as e:
        logger.error(f"Ошибка форматирования результата: {e}")
        return "❌ **Ошибка при выводе результата**"

async def validate_ticker(symbol: str) -> Dict[str, Any]:
    """Проверяет валидность тикера"""
    logger.info(f"Проверка тикера {symbol}...")
    
    try:
        exchange = detect_exchange_by_ticker(symbol)
        ticker_id = await get_or_create_ticker_id(symbol, exchange=exchange)
        
        if not ticker_id:
            return {
                "valid": False,
                "symbol": symbol,
                "error": "Тикер не найден"
            }
        
        market_data = await get_market_data_for_ticker(ticker_id, days_back=30)
        
        result = {
            "valid": True,
            "symbol": symbol,
            "exchange": exchange,
            "ticker_id": ticker_id,
            "has_data": not market_data.empty,
            "data_points": len(market_data)
        }
        
        if not market_data.empty:
            result["latest_date"] = market_data['date'].max().strftime('%Y-%m-%d')
            result["latest_price"] = float(market_data['close_price'].iloc[-1])
        
        return result
        
    except Exception as e:
        logger.error(f"Ошибка проверки тикера {symbol}: {e}")
        return {
            "valid": False,
            "symbol": symbol,
            "error": str(e)
        }

def format_ensemble_output(ensemble_result: Dict[str, Any]) -> str:
    """Форматирует вывод ансамбля моделей"""
    if "error" in ensemble_result:
        return format_prediction_output(ensemble_result)
    
    try:
        symbol = ensemble_result["symbol"]
        ensemble_pred = ensemble_result["ensemble_prediction"]
        individual_preds = ensemble_result.get("individual_predictions", {})
        sentiment_score = ensemble_result.get("sentiment_score", 0)
        
        price = ensemble_pred["price"]
        change = ensemble_pred["change_percent"]
        confidence = ensemble_pred["confidence"] * 100  # Преобразуем в проценты
        
        change_sign = "+" if change >= 0 else ""
        change_emoji = "📈" if change >= 0 else "📉"
        
        confidence_emoji = "🟢" if confidence >= 70 else "🟡" if confidence >= 50 else "🔴"
        
        result_lines = [
            f"{change_emoji} **Ансамблевый прогноз для {symbol}**",
            f"📅 Через {ensemble_result.get('days_ahead', 7)} дней:",
            f"💰 **Цена:** {price:.2f} ({change_sign}{change:.2f}%)",
            f"🎯 **Уверенность:** {confidence_emoji} {confidence:.1f}%",
        ]
        
        # Информация о моделях
        if individual_preds:
            result_lines.append(f"🧠 **Использовано моделей:** {len(individual_preds)}")
            
            # Показать основные модели
            model_names = list(individual_preds.keys())
            if model_names:
                result_lines.append(f"📊 **Модели:** {', '.join(model_names[:3])}")
        
        # Сентимент
        if abs(sentiment_score) > 0.1:
            sentiment_emoji = "😊" if sentiment_score > 0 else "😟"
            result_lines.append(f"📰 **Сентимент новостей:** {sentiment_emoji} {sentiment_score:.3f}")
        
        return "\n".join(result_lines)
        
    except KeyError as e:
        logger.error(f"Ключ отсутствует в результате ансамбля: {e}")
        return f"❌ **Ошибка форматирования ансамбля:** ключ {e} не найден."