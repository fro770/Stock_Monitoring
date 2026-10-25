"""
Основной анализатор акций
"""

import pandas as pd
import numpy as np
from datetime import datetime
from typing import List, Dict, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm

from .core.config import Config
from .core.data_loader import DataLoader
from .models.model_manager import ModelManager

class StockAnalyzer:
    """Основной анализатор акций"""
    
    def __init__(self, stock_type: int = 1, mode: int = 2, 
                 prediction_days: List[int] = None, min_confidence: float = 0.5):
        """
        Инициализация анализатора
        
        Args:
            stock_type: 1-все, 2-обыкновенные, 3-привилегированные
            mode: 1-быстрый, 2-стандартный, 3-глубокий
            prediction_days: Список дней для прогноза
            min_confidence: Минимальная уверенность (0-1)
        """
        self.stock_type = stock_type
        self.mode = mode
        self.prediction_days = prediction_days or Config.DEFAULT_PREDICTION_DAYS
        self.min_confidence = min_confidence
        
        # Инициализация компонентов
        self.data_loader = DataLoader()
        self.predictor = ModelManager.get_predictor(mode)
        
        # Кэши
        self.results_cache = {}
        self.data_cache = {}
        
        print(f"🚀 Анализатор инициализирован:")
        print(f"   📊 Тип акций: {Config.STOCK_TYPES[stock_type]}")
        print(f"   🧠 Режим анализа: {Config.MODES[mode]['name']}")
        print(f"   📅 Прогноз на дни: {self.prediction_days}")
        print(f"   🎯 Минимальная уверенность: {min_confidence*100:.0f}%")
    
    def load_tickers(self) -> List[Dict]:
        """Загружает тикеры для анализа"""
        print("📋 Загрузка тикеров...")
        tickers = self.data_loader.load_tickers_from_db(self.stock_type)
        
        if not tickers:
            print("❌ Не удалось загрузить тикеры")
            return []
        
        print(f"✅ Загружено {len(tickers)} тикеров")
        return tickers
    
    def analyze_ticker(self, ticker_info: Dict) -> Optional[Dict]:
        """Анализирует один тикер"""
        ticker = ticker_info['ticker']
        
        # Проверяем кэш результатов
        if ticker in self.results_cache:
            return self.results_cache[ticker]
        
        print(f"🔍 Анализ {ticker}...")
        
        try:
            # Получаем исторические данные
            data = self._get_ticker_data(ticker)
            
            if data is None or len(data) < Config.MIN_HISTORY_DAYS:
                print(f"⚠️  Недостаточно данных для {ticker}")
                return None
            
            last_price = float(data['close_price'].iloc[-1])
            
            if last_price <= 0 or pd.isna(last_price):
                print(f"⚠️  Некорректная цена для {ticker}: {last_price}")
                return None
            
            # Прогнозируем для каждого горизонта
            predictions = {}
            all_confidences = []
            models_used = []
            
            for days in self.prediction_days:
                try:
                    # Прогнозируем с возможностью повторных попыток
                    pred_result = ModelManager.predict_with_retry(
                        self.predictor, ticker, data, days, max_retries=2
                    )
                    
                    if pred_result and 'error' not in pred_result:
                        predictions[f'day_{days}'] = pred_result
                        all_confidences.append(pred_result.get('confidence', 0))
                        
                        # Собираем использованные модели
                        if 'models_used' in pred_result:
                            models_used.extend(pred_result['models_used'])
                    else:
                        print(f"⚠️  Ошибка прогноза для {ticker} на {days} дней")
                        predictions[f'day_{days}'] = {
                            'price': last_price,
                            'change_percent': 0,
                            'confidence': 0,
                            'error': pred_result.get('error', 'Unknown error') if pred_result else 'No result'
                        }
                except Exception as e:
                    print(f"❌ Ошибка прогноза для {ticker} на {days} дней: {e}")
                    predictions[f'day_{days}'] = {
                        'price': last_price,
                        'change_percent': 0,
                        'confidence': 0,
                        'error': str(e)
                    }
            
            # Рассчитываем средние показатели
            if predictions:
                changes = [pred.get('change_percent', 0) for pred in predictions.values() 
                          if isinstance(pred, dict) and 'change_percent' in pred]
                avg_change = np.mean(changes) if changes else 0
                
                confidences = [pred.get('confidence', 0) for pred in predictions.values() 
                             if isinstance(pred, dict) and 'confidence' in pred]
                avg_confidence = np.mean(confidences) if confidences else 0
                
                # Проверяем согласованность моделей для глубокого режима
                if self.mode == 3:
                    model_consistency = self._check_model_consistency(predictions)
                else:
                    model_consistency = 1.0
            else:
                avg_change = 0
                avg_confidence = 0
                model_consistency = 0
            
            # Формируем результат
            result = {
                'ticker': ticker,
                'name': ticker_info['name'],
                'sectype': ticker_info['sectype'],
                'type_description': ticker_info['type_description'],
                'exchange': ticker_info.get('exchange', 'MOEX'),
                'last_price': round(last_price, 2),
                'data_points': len(data),
                'avg_change_percent': round(avg_change, 2),
                'avg_confidence': round(avg_confidence, 4),
                'model_consistency': round(model_consistency, 2),
                'predictions': predictions,
                'models_used': list(set(models_used)),
                'analysis_timestamp': datetime.now().isoformat(),
                'has_enough_data': len(data) >= 100
            }
            
            # Сохраняем в кэш
            self.results_cache[ticker] = result
            
            print(f"✅ {ticker}: цена={last_price:.2f}, рост={avg_change:+.2f}%, уверенность={avg_confidence:.1%}")
            return result
            
        except Exception as e:
            print(f"❌ Критическая ошибка анализа {ticker}: {e}")
            return None
    
    def _get_ticker_data(self, ticker: str) -> Optional[pd.DataFrame]:
        """Получает данные для тикера с кэшированием"""
        if ticker in self.data_cache:
            return self.data_cache[ticker].copy()
        
        try:
            data = self.data_loader.get_ticker_data(ticker, Config.DEFAULT_HISTORY_DAYS)
            
            if not data.empty:
                self.data_cache[ticker] = data.copy()
                return data
            else:
                return None
                
        except Exception as e:
            print(f"❌ Ошибка получения данных для {ticker}: {e}")
            return None
    
    def _check_model_consistency(self, predictions: Dict) -> float:
        """Проверяет согласованность прогнозов разных моделей"""
        try:
            all_consistencies = []
            
            for day_key, pred in predictions.items():
                if isinstance(pred, dict) and 'individual_predictions' in pred:
                    individual_preds = pred['individual_predictions']
                    if individual_preds and len(individual_preds) > 1:
                        # Собираем все прогнозы цен
                        prices = [p.get('price', 0) for p in individual_preds]
                        
                        # Рассчитываем коэффициент вариации
                        mean_price = np.mean(prices)
                        std_price = np.std(prices)
                        cv = std_price / mean_price if mean_price > 0 else 1
                        
                        # Согласованность = 1 - коэффициент вариации (но не менее 0)
                        consistency = max(0, 1 - cv)
                        all_consistencies.append(consistency)
            
            return np.mean(all_consistencies) if all_consistencies else 1.0
        except Exception as e:
            print(f"⚠️  Ошибка проверки согласованности: {e}")
            return 0.8
    
    def analyze_all(self, tickers: List[Dict]) -> List[Dict]:
        """Анализирует все тикеры параллельно"""
        print(f"🚀 Запуск анализа {len(tickers)} тикеров...")
        
        results = []
        
        # Используем ThreadPoolExecutor для параллельной обработки
        with ThreadPoolExecutor(max_workers=Config.MAX_WORKERS) as executor:
            # Создаем futures
            futures = {executor.submit(self.analyze_ticker, ticker): ticker for ticker in tickers}
            
            # Используем tqdm для прогресс-бара
            with tqdm(total=len(tickers), desc="📊 Анализ тикеров", unit="тикер") as pbar:
                for future in as_completed(futures):
                    try:
                        result = future.result(timeout=Config.TICKER_TIMEOUT)
                        if result:
                            results.append(result)
                    except Exception as e:
                        ticker_info = futures[future]
                        print(f"❌ Ошибка анализа {ticker_info['ticker']}: {e}")
                    finally:
                        pbar.update(1)
        
        print(f"✅ Анализ завершен. Успешно: {len(results)}/{len(tickers)} тикеров")
        return results
    
    def filter_by_confidence(self, results: List[Dict]) -> List[Dict]:
        """Фильтрует результаты по минимальной уверенности"""
        filtered = []
        
        for result in results:
            if result.get('avg_confidence', 0) >= self.min_confidence:
                # Для глубокого режима дополнительно проверяем согласованность
                if self.mode == 3:
                    if result.get('model_consistency', 0) >= 0.7:
                        filtered.append(result)
                else:
                    filtered.append(result)
        
        print(f"🎯 После фильтрации по уверенности: {len(filtered)} тикеров")
        return filtered
    
    def get_top_results(self, results: List[Dict], top_n: int) -> List[Dict]:
        """Возвращает топ-N результатов по прогнозируемому росту"""
        if not results:
            return []
        
        # Сортируем по среднему росту
        sorted_results = sorted(
            results,
            key=lambda x: x.get('avg_change_percent', 0),
            reverse=True
        )
        
        return sorted_results[:top_n]