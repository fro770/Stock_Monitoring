"""
models/sentiment/whisper_analyzer.py
Упрощенный модуль для анализа новостей с использованием GGUF моделей
"""

import logging
import asyncio
import json
import os
import re
from typing import List, Dict, Any
from pathlib import Path
from collections import Counter

logger = logging.getLogger(__name__)

# Глобальный экземпляр модели
_llm_instance = None
_model_loaded = False

def load_gguf_model():
    """Загружает GGUF модель один раз при старте"""
    global _llm_instance, _model_loaded
    
    if _model_loaded:
        return _llm_instance
    
    try:
        from llama_cpp import Llama
        
        # Путь к модели
        model_path = "models/mistral-7B-instruct-v0.2.Q3_K.gguf"
        
        # Проверяем абсолютный путь
        if not os.path.isabs(model_path):
            # Делаем абсолютным относительно корня проекта
            project_root = Path(__file__).parent.parent.parent
            model_path = str(project_root / model_path)
        
        logger.info(f"Загрузка модели из: {model_path}")
        logger.info(f"Файл существует: {os.path.exists(model_path)}")
        
        if not os.path.exists(model_path):
            logger.error(f"Файл модели не найден: {model_path}")
            # Пробуем относительный путь
            model_path = "models/mistral-7B-instruct-v0.2.Q3_K.gguf"
            logger.info(f"Пробуем относительный путь: {model_path}")
        
        # Минимальные параметры для теста
        _llm_instance = Llama(
            model_path=model_path,
            n_ctx=1024,  # Достаточно для анализа новостей
            n_threads=4,
            n_gpu_layers=0,
            verbose=False
        )
        
        _model_loaded = True
        logger.info("✅ GGUF модель успешно загружена")
        
        # Быстрый тест
        test_response = _llm_instance("Привет", max_tokens=10, temperature=0.1)
        logger.info(f"Тестовая генерация: {test_response['choices'][0]['text'][:50]}...")
        
        return _llm_instance
        
    except Exception as e:
        logger.error(f"❌ Ошибка загрузки GGUF модели: {e}")
        _llm_instance = None
        _model_loaded = False
        return None

class SimpleNewsAnalyzer:
    """Простой анализатор новостей с поддержкой LLM"""
    
    def __init__(self):
        self.llm = None
        
    async def analyze_news_summary(self, news_list: List[Dict], analysis_type: str = "general") -> Dict[str, Any]:
        """
        Анализирует список новостей и генерирует сводку
        """
        if not news_list:
            return self._empty_result(analysis_type)
        
        try:
            # Пробуем использовать LLM если доступна
            if self.llm is None:
                self.llm = load_gguf_model()
            
            if self.llm:
                return await self._analyze_with_llm(news_list, analysis_type)
            else:
                # Fallback на простой анализ
                return await self._simple_analysis(news_list, analysis_type)
                
        except Exception as e:
            logger.error(f"Ошибка анализа новостей: {e}")
            return await self._simple_analysis(news_list, analysis_type)
    
    async def _analyze_with_llm(self, news_list: List[Dict], analysis_type: str) -> Dict[str, Any]:
        """Анализ с использованием LLM"""
        try:
            # Подготавливаем промпт
            prompt = self._create_prompt(news_list, analysis_type)
            
            # Генерируем ответ
            response = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.llm(
                    prompt,
                    max_tokens=300,
                    temperature=0.7,
                    stop=["\n\n", "###", "---"],
                    echo=False
                )
            )
            
            # Извлекаем текст
            if response and "choices" in response:
                llm_text = response["choices"][0]["text"].strip()
            else:
                llm_text = "Модель не смогла сгенерировать анализ."
            
            # Дополнительный анализ
            sentiment = self._analyze_sentiment(news_list)
            topics = self._extract_topics(news_list)
            tickers = self._extract_tickers(news_list)
            
            return {
                "summary": llm_text[:1000],
                "sentiment_score": sentiment,
                "key_topics": topics,
                "affected_tickers": tickers,
                "analysis_type": analysis_type,
                "news_count": len(news_list),
                "model_used": "gguf"
            }
            
        except Exception as e:
            logger.error(f"Ошибка LLM анализа: {e}")
            return await self._simple_analysis(news_list, analysis_type)
    
    def _create_prompt(self, news_list: List[Dict], analysis_type: str) -> str:
        """Создает промпт для анализа"""
        # Собираем краткое содержание новостей
        news_summaries = []
        for i, news in enumerate(news_list[:8], 1):
            title = news.get('title', '')[:100]
            source = news.get('source', 'неизвестно')
            news_summaries.append(f"{i}. {title} ({source})")
        
        news_text = "\n".join(news_summaries)
        
        prompts = {
            "general": f"""Проанализируй следующие финансовые новости и создай краткую сводку:

{news_text}

Твоя задача:
1. Выдели главные темы
2. Оцени общий настрой (позитивный/негативный/нейтральный)
3. Сделай краткие выводы

Формат:
ОСНОВНЫЕ ТЕМЫ: [темы]
НАСТРОЙ: [позитивный/негативный/нейтральный]
ВЫВОДЫ: [выводы]""",
            
            "sector": f"""Проанализируй новости по отраслям:

{news_text}

Выдели основные сектора и их состояние.""",
            
            "ticker": f"""Проанализируй новости по компаниям:

{news_text}

Отметь ключевые компании и влияние на них."""
        }
        
        return prompts.get(analysis_type, prompts["general"])
    
    async def _simple_analysis(self, news_list: List[Dict], analysis_type: str) -> Dict[str, Any]:
        """Простой анализ без LLM"""
        sentiment = self._analyze_sentiment(news_list)
        topics = self._extract_topics(news_list)
        tickers = self._extract_tickers(news_list)
        
        # Формируем простую сводку
        if analysis_type == "general":
            mood = "позитивный" if sentiment > 0.2 else "негативный" if sentiment < -0.2 else "нейтральный"
            summary = f"Анализ {len(news_list)} новостей. Общий настрой: {mood}. "
            if topics:
                summary += f"Ключевые темы: {', '.join(topics[:3])}. "
            if tickers:
                summary += f"Основные компании: {', '.join(tickers[:3])}."
        
        elif analysis_type == "sector":
            summary = f"Отраслевой анализ {len(news_list)} новостей. "
            if tickers:
                summary += f"Затронутые компании: {', '.join(tickers[:5])}."
        
        elif analysis_type == "ticker":
            summary = f"Анализ по компаниям: {len(news_list)} новостей. "
            if tickers:
                summary += f"Ключевые тикеры: {', '.join(tickers[:5])}."
        
        else:
            summary = f"Проанализировано {len(news_list)} новостей."
        
        return {
            "summary": summary,
            "sentiment_score": sentiment,
            "key_topics": topics,
            "affected_tickers": tickers,
            "analysis_type": analysis_type,
            "news_count": len(news_list),
            "model_used": "simple"
        }
    
    def _empty_result(self, analysis_type: str) -> Dict[str, Any]:
        """Пустой результат"""
        return {
            "summary": "Новостей для анализа не найдено.",
            "sentiment_score": 0.0,
            "key_topics": [],
            "affected_tickers": [],
            "analysis_type": analysis_type,
            "news_count": 0,
            "model_used": "none"
        }
    
    def _analyze_sentiment(self, news_list: List[Dict]) -> float:
        """Анализирует сентимент новостей"""
        try:
            from models.sentiment.analyzer import analyze_sentiment
            
            texts = []
            for news in news_list:
                title = news.get('title', '')
                if title and len(title.strip()) > 10:
                    texts.append(title[:200])
            
            if texts:
                return analyze_sentiment(texts)
            return 0.0
            
        except Exception as e:
            logger.error(f"Ошибка анализа сентимента: {e}")
            return 0.0
    
    def _extract_topics(self, news_list: List[Dict]) -> List[str]:
        """Извлекает ключевые темы"""
        try:
            all_text = " ".join([news.get('title', '') for news in news_list]).lower()
            
            stop_words = {'и', 'в', 'на', 'с', 'по', 'для', 'не', 'что', 'это', 'как'}
            words = re.findall(r'\b[а-я]{4,}\b', all_text)
            
            filtered = [w for w in words if w not in stop_words]
            word_counts = Counter(filtered)
            
            return [word for word, count in word_counts.most_common(5)]
            
        except Exception as e:
            logger.error(f"Ошибка извлечения тем: {e}")
            return []
    
    def _extract_tickers(self, news_list: List[Dict]) -> List[str]:
        """Извлекает тикеры"""
        try:
            all_text = " ".join([f"{n.get('title', '')} {n.get('content', '')}" for n in news_list]).upper()
            
            ticker_pattern = r'\b[A-Z]{2,5}\b'
            possible = re.findall(ticker_pattern, all_text)
            
            common = {'THE', 'AND', 'FOR', 'WITH', 'FROM', 'THIS', 'THAT'}
            filtered = [t for t in possible if t not in common]
            
            ticker_counts = Counter(filtered)
            return [ticker for ticker, count in ticker_counts.most_common(10)]
            
        except Exception as e:
            logger.error(f"Ошибка извлечения тикеров: {e}")
            return []

# Создаем глобальный экземпляр при импорте
news_analyzer = SimpleNewsAnalyzer()

async def get_news_analyzer() -> SimpleNewsAnalyzer:
    """Возвращает анализатор новостей"""
    return news_analyzer

async def analyze_news_for_bot(news_list: List[Dict], analysis_type: str = "general") -> Dict[str, Any]:
    """Основная функция для анализа новостей"""
    analyzer = await get_news_analyzer()
    return await analyzer.analyze_news_summary(news_list, analysis_type)

def format_news_summary_for_telegram(analysis_result: Dict[str, Any]) -> str:
    """Форматирует результат для Telegram"""
    
    summary = analysis_result.get("summary", "Нет сводки")
    sentiment = analysis_result.get("sentiment_score", 0)
    news_count = analysis_result.get("news_count", 0)
    analysis_type = analysis_result.get("analysis_type", "general")
    
    # Эмодзи для сентимента
    if sentiment > 0.2:
        sentiment_emoji = "📈"
    elif sentiment < -0.2:
        sentiment_emoji = "📉"
    else:
        sentiment_emoji = "📊"
    
    # Заголовок
    titles = {
        "general": "📰 СВОДКА НОВОСТЕЙ",
        "sector": "🏭 ОТРАСЛЕВОЙ АНАЛИЗ",
        "ticker": "🏢 АНАЛИЗ ПО КОМПАНИЯМ"
    }
    
    title = titles.get(analysis_type, "📊 АНАЛИЗ")
    
    # Формируем сообщение
    message = f"{title}\n"
    message += f"{'='*40}\n\n"
    message += f"{summary}\n\n"
    
    # Детали
    if "key_topics" in analysis_result and analysis_result["key_topics"]:
        message += f"🔑 Темы: {', '.join(analysis_result['key_topics'][:3])}\n"
    
    if "affected_tickers" in analysis_result and analysis_result["affected_tickers"]:
        message += f"🏢 Компании: {', '.join(analysis_result['affected_tickers'][:5])}\n"
    
    message += f"\n{sentiment_emoji} Настрой рынка: {sentiment:.2f}\n"
    message += f"📊 Новостей: {news_count}\n"
    message += f"\n{'='*40}\n"
    message += "🤖 Анализ с использованием ИИ"
    
    return message

# Предзагрузка модели при импорте модуля
try:
    load_gguf_model()
    logger.info("✅ Модель предзагружена")
except Exception as e:
    logger.warning(f"Не удалось предзагрузить модель: {e}")