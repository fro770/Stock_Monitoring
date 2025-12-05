"""
Загрузчик данных для анализа
"""

import sqlite3
import pandas as pd
from typing import List, Dict, Optional
from .config import Config

# Используем рабочий клиент
try:
    from .moex_client import WorkingMOEXClient
except ImportError:
    # Fallback на старый клиент если новый не доступен
    try:
        from .moex_client import MOEXClient as WorkingMOEXClient
    except ImportError:
        # Создаем заглушку если вообще ничего не работает
        class WorkingMOEXClient:
            def get_price_history(self, ticker, days):
                return pd.DataFrame()
            def validate_ticker(self, ticker):
                return {'valid': False, 'error': 'Клиент не инициализирован'}

class DataLoader:
    """Загрузчик данных для анализа"""
    
    def __init__(self):
        self.moex_client = WorkingMOEXClient()
        self.db_path = Config.DB_PATH
    
    def load_tickers_from_db(self, stock_type: int = 1) -> List[Dict]:
        """
        Загружает тикеры из базы данных
        
        Args:
            stock_type: 1-все, 2-обыкновенные, 3-привилегированные
        
        Returns:
            Список словарей с информацией о тикерах
        """
        try:
            conn = sqlite3.connect(self.db_path)
            
            # Формируем запрос в зависимости от типа акций
            if stock_type == 1:  # Все акции
                query = """
                SELECT ticker, name, sectype, type_description 
                FROM stocks 
                ORDER BY ticker
                """
                params = ()
            elif stock_type == 2:  # Только обыкновенные
                query = """
                SELECT ticker, name, sectype, type_description 
                FROM stocks 
                WHERE sectype = '1' 
                ORDER BY ticker
                """
                params = ()
            else:  # Только привилегированные
                query = """
                SELECT ticker, name, sectype, type_description 
                FROM stocks 
                WHERE sectype = '2' 
                ORDER BY ticker
                """
                params = ()
            
            df = pd.read_sql_query(query, conn, params=params)
            conn.close()
            
            tickers = []
            for _, row in df.iterrows():
                tickers.append({
                    'ticker': row['ticker'],
                    'name': row['name'],
                    'sectype': row['sectype'],
                    'type_description': row['type_description'],
                    'exchange': 'MOEX'
                })
            
            print(f"📊 Загружено {len(tickers)} тикеров из базы данных")
            return tickers
            
        except Exception as e:
            print(f"❌ Ошибка загрузки тикеров: {e}")
            return []
    
    def get_ticker_data(self, ticker: str, days: int = 365) -> pd.DataFrame:
        """
        Получает исторические данные для тикера с MOEX
        
        Args:
            ticker: Тикер акции
            days: Количество дней истории
        
        Returns:
            DataFrame с данными или пустой DataFrame при ошибке
        """
        try:
            print(f"📥 Загрузка данных для {ticker}...")
            data = self.moex_client.get_price_history(ticker, days)
            
            if data.empty:
                print(f"⚠️  Нет данных для {ticker}")
                return pd.DataFrame()
            
            # Убедимся, что есть колонка close_price
            if 'close_price' not in data.columns:
                print(f"⚠️  Нет данных о ценах для {ticker}")
                return pd.DataFrame()
            
            print(f"✅ Получено {len(data)} дней данных для {ticker}")
            
            if not data.empty:
                print(f"   📅 Период: {data['Date'].min().date()} - {data['Date'].max().date()}")
                print(f"   💰 Последняя цена: {data['close_price'].iloc[-1]:.2f}")
            
            return data
            
        except Exception as e:
            print(f"❌ Ошибка получения данных для {ticker}: {e}")
            return pd.DataFrame()
    
    def validate_ticker_data(self, ticker: str, min_days: int = 30) -> Dict:
        """
        Проверяет наличие и качество данных для тикера
        
        Args:
            ticker: Тикер акции
            min_days: Минимальное количество дней данных
        
        Returns:
            Словарь с результатами проверки
        """
        try:
            # Проверяем валидность тикера
            validation = self.moex_client.validate_ticker(ticker)
            
            if not validation['valid']:
                return {
                    'valid': False,
                    'ticker': ticker,
                    'error': validation.get('error', 'Тикер не найден')
                }
            
            # Получаем данные
            data = self.get_ticker_data(ticker, days=min_days + 30)
            
            if data.empty or len(data) < min_days:
                return {
                    'valid': False,
                    'ticker': ticker,
                    'error': f'Недостаточно данных: {len(data)} дней (требуется {min_days})'
                }
            
            # Проверяем качество данных
            last_price = data['close_price'].iloc[-1]
            if pd.isna(last_price) or last_price <= 0:
                return {
                    'valid': False,
                    'ticker': ticker,
                    'error': f'Некорректная цена: {last_price}'
                }
            
            return {
                'valid': True,
                'ticker': ticker,
                'name': validation.get('name', ticker),
                'data_points': len(data),
                'last_price': float(last_price),
                'has_enough_data': len(data) >= min_days,
                'date_range': {
                    'start': data['Date'].min().strftime('%Y-%m-%d'),
                    'end': data['Date'].max().strftime('%Y-%m-%d')
                }
            }
            
        except Exception as e:
            return {
                'valid': False,
                'ticker': ticker,
                'error': str(e)
            }
    
    def quick_test(self, count: int = 10):
        """Быстрый тест загрузки данных"""
        print("🧪 БЫСТРЫЙ ТЕСТ ЗАГРУЗКИ ДАННЫХ")
        print("=" * 50)
        
        # Загружаем тикеры
        tickers = self.load_tickers_from_db()
        
        if not tickers:
            print("❌ Не удалось загрузить тикеры")
            return
        
        # Тестируем первые N тикеров
        test_tickers = tickers[:count]
        
        success_count = 0
        failed_tickers = []
        
        for ticker_info in test_tickers:
            ticker = ticker_info['ticker']
            print(f"\n📊 {ticker} ({ticker_info['name']})...")
            
            try:
                # Пробуем получить данные
                data = self.get_ticker_data(ticker, days=10)
                
                if data.empty:
                    print(f"   ❌ Нет данных")
                    failed_tickers.append(ticker)
                else:
                    print(f"   ✅ Данные: {len(data)} записей")
                    print(f"      Цена: {data['close_price'].iloc[-1]:.2f}")
                    success_count += 1
                    
            except Exception as e:
                print(f"   ❌ Ошибка: {e}")
                failed_tickers.append(ticker)
        
        print(f"\n📋 ИТОГИ:")
        print(f"   ✅ Успешно: {success_count}/{len(test_tickers)}")
        print(f"   ❌ Ошибок: {len(failed_tickers)}")
        
        if failed_tickers:
            print(f"   📝 Проблемные тикеры: {failed_tickers}")
        
        return success_count > 0