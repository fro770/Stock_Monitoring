"""
Модуль для анализа сентимента и генерации новостных сводок
Теперь с интеграцией LLM анализатора
"""

import logging
import asyncio
from typing import List, Dict, Any
import torch
from transformers import pipeline, AutoTokenizer, AutoModelForSequenceClassification

logger = logging.getLogger(__name__)

# Глобальные переменные для моделей
sentiment_pipeline = None
summarizer_pipeline = None

def init_models():
    """Инициализирует модели для анализа"""
    global sentiment_pipeline, summarizer_pipeline
    
    try:
        # FinBERT для сентимента
        logger.info("Инициализация FinBERT модели...")
        sentiment_pipeline = pipeline(
            "sentiment-analysis",
            model="models/finbert-tone",
            tokenizer="models/finbert-tone"
        )
        
        logger.info("Модели инициализированы")
        
    except Exception as e:
        logger.error(f"Ошибка инициализации моделей: {e}")

def analyze_sentiment(texts: List[str]) -> float:
    """
    Анализирует сентимент текстов.
    Возвращает средний сентимент от -1.0 до +1.0
    """
    if not texts:
        return 0.0
    
    if sentiment_pipeline is None:
        init_models()
    
    try:
        sentiments = []
        
        for text in texts:
            if not text or len(text.strip()) < 10:
                continue
                
            result = sentiment_pipeline(text[:512])[0]  # Ограничиваем длину
            
            # Преобразуем LABEL в числовое значение
            label = result['label']
            score = result['score']
            
            if 'positive' in label.lower():
                sentiment_value = score
            elif 'negative' in label.lower():
                sentiment_value = -score
            else:
                sentiment_value = 0
            
            sentiments.append(sentiment_value)
        
        if not sentiments:
            return 0.0
        
        return float(sum(sentiments) / len(sentiments))
        
    except Exception as e:
        logger.error(f"Ошибка анализа сентимента: {e}")
        return 0.0

async def analyze_news_summary(news_list: List[Dict]) -> str:
    """
    Анализирует список новостей и генерирует краткую сводку
    Теперь использует GGUF анализатор
    """
    try:
        # Используем новый GGUF анализатор новостей
        from models.sentiment.whisper_analyzer import analyze_news_for_bot, format_news_summary_for_telegram
        
        # Получаем расширенный анализ
        analysis_result = await analyze_news_for_bot(news_list, analysis_type="general")
        
        # Форматируем для Telegram
        return format_news_summary_for_telegram(analysis_result)
        
    except ImportError as e:
        # Fallback на старую логику
        logger.warning(f"GGUF анализатор новостей не доступен: {e}")
        return await _legacy_news_summary(news_list)
    except Exception as e:
        logger.error(f"Ошибка анализа новостей: {e}")
        return f"❌ Ошибка анализа новостей: {str(e)}"

async def _legacy_news_summary(news_list: List[Dict]) -> str:
    """Старой версии анализа (для совместимости)"""
    if not news_list:
        return "Новостей для анализа не найдено."
    
    try:
        # Собираем все заголовки
        titles = [news.get('title', '') for news in news_list if news.get('title')]
        
        if not titles:
            return "Недостаточно данных для анализа."
        
        # Анализируем общий сентимент
        overall_sentiment = analyze_sentiment(titles)
        
        # Подсчитываем частоту упоминаний
        ticker_mentions = {}
        for news in news_list:
            content = f"{news.get('title', '')} {news.get('content', '')}".upper()
            import re
            tickers = re.findall(r'\b[A-Z]{2,5}\b', content)
            for ticker in tickers:
                if ticker in ['THE', 'AND', 'FOR', 'WITH', 'FROM']:
                    continue
                ticker_mentions[ticker] = ticker_mentions.get(ticker, 0) + 1
        
        # Находим самые частые тикеры
        top_tickers = sorted(ticker_mentions.items(), key=lambda x: x[1], reverse=True)[:5]
        
        # Формируем сводку
        sentiment_emoji = "😊" if overall_sentiment > 0.1 else "😟" if overall_sentiment < -0.1 else "😐"
        
        summary = f"📰 Обзор {len(news_list)} новостей\n"
        summary += f"{'='*30}\n\n"
        summary += f"Общий настрой: {sentiment_emoji} "
        
        if overall_sentiment > 0.2:
            summary += "Позитивный, рынок настроен оптимистично."
        elif overall_sentiment > 0:
            summary += "Слегка позитивный."
        elif overall_sentiment < -0.2:
            summary += "Негативный, преобладают опасения."
        elif overall_sentiment < 0:
            summary += "Слегка негативный."
        else:
            summary += "Нейтральный, без явного тренда."
        
        if top_tickers:
            summary += f"\n\nЧаще всего упоминаются: {', '.join([t[0] for t in top_tickers[:3]])}"
        
        return summary
        
    except Exception as e:
        logger.error(f"Ошибка анализа новостей: {e}")
        return "Не удалось проанализировать новости."

async def get_sector_analysis(news_list: List[Dict]) -> str:
    """
    Специальный анализ по секторам
    """
    try:
        from models.sentiment.whisper_analyzer import analyze_news_for_bot, format_news_summary_for_telegram
        
        analysis_result = await analyze_news_for_bot(news_list, analysis_type="sector")
        return format_news_summary_for_telegram(analysis_result)
        
    except Exception as e:
        logger.error(f"Ошибка отраслевого анализа: {e}")
        return "Не удалось выполнить отраслевой анализ."

async def get_ticker_analysis(news_list: List[Dict]) -> str:
    """
    Специальный анализ по компаниям/тикерам
    """
    try:
        from models.sentiment.whisper_analyzer import analyze_news_for_bot, format_news_summary_for_telegram
        
        analysis_result = await analyze_news_for_bot(news_list, analysis_type="ticker")
        return format_news_summary_for_telegram(analysis_result)
        
    except Exception as e:
        logger.error(f"Ошибка анализа по компаниям: {e}")
        return "Не удалось выполнить анализ по компаниям."

def get_market_trend(news_list: List[Dict]) -> Dict[str, Any]:
    """
    Определяет тренд рынка на основе новостей
    """
    if not news_list:
        return {"trend": "neutral", "confidence": 0.0}
    
    try:
        # Используем LLM анализатор если доступен
        try:
            from models.sentiment.whisper_analyzer import analyze_news_for_bot
            import asyncio
            
            # Запускаем анализ в event loop
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            analysis_result = loop.run_until_complete(
                analyze_news_for_bot(news_list, analysis_type="general")
            )
            loop.close()
            
            sentiment = analysis_result.get("sentiment_score", 0)
            
            if sentiment > 0.2:
                return {"trend": "bullish", "confidence": min(1.0, sentiment)}
            elif sentiment < -0.2:
                return {"trend": "bearish", "confidence": min(1.0, -sentiment)}
            else:
                return {"trend": "neutral", "confidence": 0.5}
                
        except:
            # Fallback на простой анализ ключевых слов
            positive_keywords = ['рост', 'выше', 'прибыль', 'успех', 'позитивно', 'оптимизм']
            negative_keywords = ['падение', 'ниже', 'убыток', 'проблемы', 'негативно', 'пессимизм']
            
            titles = [news.get('title', '').lower() for news in news_list]
            
            positive_count = sum(1 for title in titles if any(kw in title for kw in positive_keywords))
            negative_count = sum(1 for title in titles if any(kw in title for kw in negative_keywords))
            
            total = positive_count + negative_count
            
            if total == 0:
                return {"trend": "neutral", "confidence": 0.0}
            
            if positive_count > negative_count:
                confidence = positive_count / total
                return {"trend": "bullish", "confidence": confidence}
            elif negative_count > positive_count:
                confidence = negative_count / total
                return {"trend": "bearish", "confidence": confidence}
            else:
                return {"trend": "neutral", "confidence": 0.5}
                
    except Exception as e:
        logger.error(f"Ошибка определения тренда: {e}")
        return {"trend": "neutral", "confidence": 0.0}

# Инициализация при импорте
init_models()