"""
Рабочий клиент для MOEX API (использует только candles endpoint)
"""

import requests
import pandas as pd
from datetime import datetime, time, timedelta
from typing import Optional, Dict, List
import logging
from .config import Config

logger = logging.getLogger(__name__)

class WorkingMOEXClient:
    """Рабочий клиент для MOEX API, использующий candles endpoint"""
    
    def __init__(self):
        self.base_url = Config.MOEX_BASE_URL
        self.session = requests.Session()
        self.session.timeout = Config.MOEX_TIMEOUT
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json'
        })
    
    def _make_request(self, url: str, params: dict = None) -> Optional[dict]:
        """Выполняет запрос к MOEX API"""
        for attempt in range(Config.MOEX_MAX_RETRIES):
            try:
                response = self.session.get(url, params=params, timeout=Config.MOEX_TIMEOUT)
                
                if response.status_code == 200:
                    return response.json()
                else:
                    logger.warning(f"HTTP {response.status_code} для {url}")
                    
            except requests.exceptions.Timeout:
                logger.warning(f"Таймаут запроса (попытка {attempt+1})")
                if attempt == Config.MOEX_MAX_RETRIES - 1:
                    return None
                time.sleep(1 * (attempt + 1))
                
            except Exception as e:
                logger.error(f"Ошибка запроса: {e}")
                if attempt == Config.MOEX_MAX_RETRIES - 1:
                    return None
                time.sleep(1 * (attempt + 1))
        
        return None
    
    def get_available_tickers(self, limit: int = 100) -> List[Dict]:
        """Получает список доступных тикеров"""
        try:
            url = f"{self.base_url}/engines/stock/markets/shares/boards/TQBR/securities.json"
            params = {
                'iss.meta': 'off',
                'limit': limit,
                'start': 0
            }
            
            data = self._make_request(url, params)
            if not data or 'securities' not in data:
                return []
            
            securities_data = data['securities']['data']
            columns = data['securities']['columns']
            
            tickers = []
            for row in securities_data:
                info = dict(zip(columns, row))
                tickers.append({
                    'ticker': info.get('SECID', ''),
                    'name': info.get('SHORTNAME', info.get('NAME', '')),
                    'boardid': info.get('BOARDID', 'TQBR'),
                    'isin': info.get('ISIN', '')
                })
            
            return tickers
            
        except Exception as e:
            logger.error(f"Ошибка получения списка тикеров: {e}")
            return []
    
    def get_price_history(self, ticker: str, days: int = 365) -> pd.DataFrame:
        """
        Получает историю цен через candles endpoint
        
        Args:
            ticker: Тикер акции (SBER, GAZP, etc.)
            days: Количество дней истории
        
        Returns:
            DataFrame с колонками: Date, open_price, high_price, low_price, close_price, volume
        """
        try:
            # Рассчитываем даты
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days)
            
            # Используем candles endpoint
            url = f"{self.base_url}/engines/stock/markets/shares/securities/{ticker}/candles.json"
            
            params = {
                'from': start_date.strftime('%Y-%m-%d'),
                'till': end_date.strftime('%Y-%m-%d'),
                'interval': 24,  # Дневные свечи
                'iss.meta': 'off',
                'lang': 'ru'
            }
            
            logger.info(f"Загрузка истории для {ticker} ({days} дней)")
            
            all_data = []
            start = 0
            
            while True:
                params['start'] = start
                data = self._make_request(url, params)
                
                if not data or 'candles' not in data:
                    break
                
                candles_data = data['candles']['data']
                if not candles_data:
                    break
                
                all_data.extend(candles_data)
                
                # Если получено меньше 100 записей, значит это последняя страница
                if len(candles_data) < 100:
                    break
                
                start += 100
                # Короткая пауза между запросами
                import time
                time.sleep(0.1)
            
            if not all_data:
                logger.warning(f"Нет данных для {ticker}")
                return pd.DataFrame()
            
            # Создаем DataFrame
            columns = data['candles']['columns']
            df = pd.DataFrame(all_data, columns=columns)
            
            # Переименовываем колонки
            column_mapping = {
                'begin': 'Date',
                'open': 'open_price',
                'high': 'high_price',
                'low': 'low_price',
                'close': 'close_price',
                'volume': 'volume',
                'value': 'value'
            }
            
            # Применяем только существующие колонки
            rename_dict = {}
            for old_col, new_col in column_mapping.items():
                if old_col in df.columns:
                    rename_dict[old_col] = new_col
            
            df = df.rename(columns=rename_dict)
            
            # Преобразуем дату
            if 'Date' in df.columns:
                df['Date'] = pd.to_datetime(df['Date'])
            
            # Сортируем по дате
            df = df.sort_values('Date')
            
            # Удаляем дубликаты
            df = df.drop_duplicates(subset=['Date'])
            
            # Проверяем наличие нужных колонок
            if 'close_price' not in df.columns:
                logger.warning(f"Нет колонки close_price для {ticker}")
                return pd.DataFrame()
            
            # Выбираем колонки
            all_cols = ['Date', 'close_price']
            for col in ['open_price', 'high_price', 'low_price', 'volume', 'value']:
                if col in df.columns:
                    all_cols.append(col)
            
            df = df[all_cols]
            
            # Удаляем строки с нулевой ценой
            df = df[df['close_price'] > 0]
            
            logger.info(f"✅ Получено {len(df)} записей для {ticker}")
            
            return df
            
        except Exception as e:
            logger.error(f"Ошибка получения истории для {ticker}: {e}")
            return pd.DataFrame()
    
    def get_current_price(self, ticker: str) -> Optional[float]:
        """Получает текущую цену акции"""
        try:
            # Получаем последнюю свечу
            data = self.get_price_history(ticker, days=5)
            
            if not data.empty and 'close_price' in data.columns:
                return float(data['close_price'].iloc[-1])
            
            return None
            
        except Exception as e:
            logger.error(f"Ошибка получения текущей цены для {ticker}: {e}")
            return None
    
    def validate_ticker(self, ticker: str) -> Dict:
        """Проверяет валидность тикера"""
        try:
            # Пробуем получить данные для тикера
            data = self.get_price_history(ticker, days=10)
            
            if data.empty:
                return {
                    'valid': False,
                    'ticker': ticker,
                    'error': 'Нет данных для тикера'
                }
            
            # Пробуем получить информацию о бумаге из списка
            ticker_info = self._get_ticker_info_from_list(ticker)
            
            return {
                'valid': True,
                'ticker': ticker,
                'name': ticker_info.get('name', ticker) if ticker_info else ticker,
                'has_data': True,
                'data_points': len(data),
                'last_price': float(data['close_price'].iloc[-1]) if not data.empty else None,
                'date_range': {
                    'start': data['Date'].min().strftime('%Y-%m-%d') if not data.empty else None,
                    'end': data['Date'].max().strftime('%Y-%m-%d') if not data.empty else None
                }
            }
            
        except Exception as e:
            return {
                'valid': False,
                'ticker': ticker,
                'error': str(e)
            }
    
    def _get_ticker_info_from_list(self, ticker: str) -> Optional[Dict]:
        """Получает информацию о тикере из списка доступных"""
        try:
            tickers = self.get_available_tickers(limit=500)
            for t in tickers:
                if t['ticker'] == ticker:
                    return t
            return None
        except:
            return None
    
    def test_tickers(self, tickers: List[str]) -> Dict:
        """Тестирует несколько тикеров"""
        results = {
            'total': len(tickers),
            'success': 0,
            'failed': 0,
            'details': {}
        }
        
        for ticker in tickers:
            try:
                data = self.get_price_history(ticker, days=5)
                
                if data.empty:
                    results['details'][ticker] = {
                        'status': 'failed',
                        'error': 'Нет данных'
                    }
                    results['failed'] += 1
                else:
                    results['details'][ticker] = {
                        'status': 'success',
                        'records': len(data),
                        'last_price': float(data['close_price'].iloc[-1]) if not data.empty else None
                    }
                    results['success'] += 1
                    
            except Exception as e:
                results['details'][ticker] = {
                    'status': 'error',
                    'error': str(e)
                }
                results['failed'] += 1
        
        return results


# Тестирование
if __name__ == "__main__":
    # Настройка логирования
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    client = WorkingMOEXClient()
    
    print("🧪 ТЕСТ РАБОЧЕГО MOEX КЛИЕНТА")
    print("=" * 60)
    
    # Тестовые тикеры
    test_tickers = ['SBER', 'GAZP', 'LKOH', 'ROSN', 'VTBR', 'YNDX', 'GMKN', 'NVTK']
    
    print(f"\n📊 Тестирование {len(test_tickers)} тикеров...")
    
    results = client.test_tickers(test_tickers)
    
    print(f"\n📋 Результаты:")
    print(f"   ✅ Успешно: {results['success']}/{results['total']}")
    print(f"   ❌ Ошибок: {results['failed']}/{results['total']}")
    
    print(f"\n📈 Детали:")
    for ticker, info in results['details'].items():
        if info['status'] == 'success':
            print(f"   ✅ {ticker}: {info['records']} записей, цена: {info['last_price']:.2f}")
        else:
            print(f"   ❌ {ticker}: {info.get('error', 'Ошибка')}")
    
    # Тест получения полной истории
    print(f"\n📅 Полная история для SBER:")
    data = client.get_price_history('SBER', days=30)
    if not data.empty:
        print(f"   ✅ Получено: {len(data)} записей")
        print(f"   📅 Период: {data['Date'].min().date()} - {data['Date'].max().date()}")
        print(f"   💰 Цены: {data['close_price'].min():.2f} - {data['close_price'].max():.2f}")
        print(f"   📊 Колонки: {list(data.columns)}")
    else:
        print(f"   ❌ Нет данных")
    
    print("\n" + "=" * 60)
    print("📋 ИНСТРУКЦИЯ:")
    print("-" * 60)
    print("1. Этот клиент использует только candles endpoint")
    print("2. Он работает надежно для большинства тикеров")
    print("3. Для использования в проекте:")
    print("   from .working_moex_client import WorkingMOEXClient")
    print("   client = WorkingMOEXClient()")
    print("=" * 60)