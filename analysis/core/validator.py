"""
Валидатор данных системы
"""

import os
import sqlite3
import pandas as pd
from datetime import datetime
from typing import Dict, List, Optional
import logging

from .config import Config
from .data_loader import DataLoader

# Импортируем правильный клиент
try:
    from .moex_client import WorkingMOEXClient as MOEXClient
except ImportError:
    try:
        from .moex_client import MOEXClient
    except ImportError:
        # Создаем заглушку если клиент не доступен
        class MOEXClient:
            def validate_ticker(self, ticker):
                return {'valid': False, 'error': 'Клиент не доступен'}
            def get_security_info(self, ticker):
                return None
            def get_current_price(self, ticker):
                return None

logger = logging.getLogger(__name__)


class DataValidator:
    """Класс для проверки и валидации данных"""
    
    def __init__(self):
        self.data_loader = DataLoader()
        self.moex_client = MOEXClient()
        self.db_path = Config.DB_PATH
    
    def check_database(self) -> Dict:
        """
        Проверяет базу данных на целостность
        
        Returns:
            Словарь с результатами проверки
        """
        print("🔍 Проверка базы данных...")
        
        results = {
            'db_exists': False,
            'tables_exist': False,
            'stocks_count': 0,
            'stocks_valid': False,
            'missing_tables': [],
            'errors': []
        }
        
        try:
            # Проверяем существование файла БД
            if not os.path.exists(self.db_path):
                results['errors'].append(f"Файл базы данных не найден: {self.db_path}")
                print(f"❌ Файл БД не найден: {self.db_path}")
                return results
            
            results['db_exists'] = True
            print(f"✅ Файл БД найден: {self.db_path}")
            
            # Подключаемся к базе
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Проверяем существование таблиц
            expected_tables = ['stocks', 'price_history', 'monitoring', 'notes']
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            existing_tables = [row[0] for row in cursor.fetchall()]
            
            results['missing_tables'] = [t for t in expected_tables if t not in existing_tables]
            
            if results['missing_tables']:
                print(f"⚠️  Отсутствуют таблицы: {results['missing_tables']}")
            else:
                results['tables_exist'] = True
                print("✅ Все таблицы существуют")
            
            # Проверяем таблицу stocks
            if 'stocks' in existing_tables:
                # Получаем количество записей
                cursor.execute("SELECT COUNT(*) FROM stocks")
                results['stocks_count'] = cursor.fetchone()[0]
                
                # Проверяем структуру таблицы
                cursor.execute("PRAGMA table_info(stocks)")
                columns = [row[1] for row in cursor.fetchall()]
                expected_columns = ['ticker', 'name', 'sectype', 'type_description']
                
                missing_columns = [col for col in expected_columns if col not in columns]
                if missing_columns:
                    results['errors'].append(f"В таблице stocks отсутствуют колонки: {missing_columns}")
                    print(f"❌ Отсутствуют колонки: {missing_columns}")
                else:
                    results['stocks_valid'] = True
                    print(f"✅ Таблица stocks содержит {results['stocks_count']} записей")
                
                # Проверяем наличие дубликатов тикеров
                cursor.execute("SELECT ticker, COUNT(*) FROM stocks GROUP BY ticker HAVING COUNT(*) > 1")
                duplicates = cursor.fetchall()
                if duplicates:
                    results['errors'].append(f"Найдены дубликаты тикеров: {[d[0] for d in duplicates]}")
                    print(f"⚠️  Найдены дубликаты тикеров: {[d[0] for d in duplicates]}")
                
                # Проверяем пустые значения
                for column in expected_columns:
                    cursor.execute(f"SELECT COUNT(*) FROM stocks WHERE {column} IS NULL OR {column} = ''")
                    null_count = cursor.fetchone()[0]
                    if null_count > 0:
                        print(f"⚠️  В колонке {column}: {null_count} пустых значений")
            
            # Проверяем индексы
            cursor.execute("SELECT name FROM sqlite_master WHERE type='index'")
            indexes = [row[0] for row in cursor.fetchall()]
            print(f"📊 Найдено индексов: {len(indexes)}")
            
            # Проверяем размер базы
            db_size = os.path.getsize(self.db_path) / 1024  # Размер в КБ
            print(f"📦 Размер БД: {db_size:.1f} КБ")
            
            conn.close()
            
            # Выводим сводку
            self._print_database_summary(results)
            
        except sqlite3.Error as e:
            results['errors'].append(f"Ошибка SQLite: {e}")
            print(f"❌ Ошибка SQLite: {e}")
        except Exception as e:
            results['errors'].append(f"Общая ошибка: {e}")
            print(f"❌ Общая ошибка: {e}")
        
        return results
    
    def _print_database_summary(self, results: Dict):
        """Выводит сводку проверки базы данных"""
        print("\n📋 СВОДКА ПРОВЕРКИ БАЗЫ ДАННЫХ")
        print("─" * 50)
        
        if not results['db_exists']:
            print("❌ База данных не найдена")
            return
        
        print(f"📁 Файл: {self.db_path}")
        print(f"📊 Таблиц: {'✓' if results['tables_exist'] else '✗'}")
        print(f"📈 Акций: {results['stocks_count']}")
        
        if results['stocks_count'] > 0:
            # Показываем примеры тикеров
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                cursor.execute("SELECT ticker, name, sectype FROM stocks ORDER BY ticker LIMIT 5")
                sample = cursor.fetchall()
                conn.close()
                
                print("\n📝 Примеры тикеров:")
                for ticker, name, sectype in sample:
                    type_desc = {
                        '1': 'Обыкн.',
                        '2': 'Привил.',
                        None: 'Неизв.'
                    }.get(sectype, sectype)
                    print(f"  {ticker:6s} - {name[:30]:30s} [{type_desc}]")
            except:
                pass
        
        if results['errors']:
            print(f"\n⚠️  Найдено ошибок: {len(results['errors'])}")
            for error in results['errors'][:3]:  # Показываем только первые 3
                print(f"  • {error}")
        
        print("─" * 50)
    
    def check_tickers(self, sample_size: int = 10) -> Dict:
        """
        Проверяет тикеры из базы данных
        
        Args:
            sample_size: Количество тикеров для проверки
        
        Returns:
            Словарь с результатами проверки
        """
        print(f"🔍 Проверка тикеров (выборка: {sample_size})...")
        
        results = {
            'total_tickers': 0,
            'checked_tickers': 0,
            'valid_tickers': 0,
            'invalid_tickers': [],
            'details': {}
        }
        
        try:
            # Загружаем тикеры из базы
            tickers = self.data_loader.load_tickers_from_db(stock_type=1)
            results['total_tickers'] = len(tickers)
            
            if not tickers:
                print("❌ Нет тикеров для проверки")
                return results
            
            print(f"✅ Загружено {len(tickers)} тикеров")
            
            # Проверяем выборку тикеров
            import random
            if len(tickers) > sample_size:
                sample_tickers = random.sample(tickers, sample_size)
            else:
                sample_tickers = tickers
            
            for i, ticker_info in enumerate(sample_tickers, 1):
                ticker = ticker_info['ticker']
                print(f"  {i:2d}. {ticker}...", end=" ", flush=True)
                
                # Используем data_loader для проверки (он уже использует правильный клиент)
                data = self.data_loader.get_ticker_data(ticker, days=10)
                
                results['checked_tickers'] += 1
                
                if not data.empty and len(data) > 0:
                    results['valid_tickers'] += 1
                    results['details'][ticker] = {
                        'valid': True,
                        'data_points': len(data),
                        'last_price': data['close_price'].iloc[-1] if 'close_price' in data.columns else None
                    }
                    print("✅ OK")
                else:
                    results['invalid_tickers'].append(ticker)
                    results['details'][ticker] = {
                        'valid': False,
                        'error': 'Нет данных'
                    }
                    print("❌ ERROR")
            
            # Выводим сводку
            print(f"\n📋 Сводка проверки:")
            print(f"  ✅ Валидных: {results['valid_tickers']}/{results['checked_tickers']}")
            print(f"  ❌ Невалидных: {len(results['invalid_tickers'])}")
            
            if results['invalid_tickers']:
                print(f"  📝 Проблемные тикеры: {results['invalid_tickers']}")
            
            # Проверяем процент валидных
            if results['checked_tickers'] > 0:
                valid_percent = (results['valid_tickers'] / results['checked_tickers']) * 100
                if valid_percent > 90:
                    print(f"✅ Качество данных: отличное ({valid_percent:.1f}% валидных)")
                elif valid_percent > 70:
                    print(f"⚠️  Качество данных: удовлетворительное ({valid_percent:.1f}% валидных)")
                else:
                    print(f"❌ Качество данных: плохое ({valid_percent:.1f}% валидных)")
        
        except Exception as e:
            print(f"❌ Ошибка проверки тикеров: {e}")
            results['errors'] = str(e)
        
        return results
    
    def check_moex_connection(self) -> Dict:
        """
        Проверяет подключение к MOEX API
        
        Returns:
            Словарь с результатами проверки
        """
        print("🌐 Проверка подключения к MOEX API...")
        
        results = {
            'moex_accessible': False,
            'response_time': 0,
            'test_tickers': []
        }
        
        try:
            # Тестовые тикеры
            test_tickers = ['SBER', 'GAZP', 'LKOH', 'VTBR', 'ROSN']
            
            start_time = datetime.now()
            
            for ticker in test_tickers:
                print(f"  📡 {ticker}...", end=" ", flush=True)
                
                try:
                    # Используем data_loader для проверки
                    data = self.data_loader.get_ticker_data(ticker, days=5)
                    
                    if not data.empty and len(data) > 0:
                        results['test_tickers'].append({
                            'ticker': ticker,
                            'status': 'success',
                            'data_points': len(data),
                            'last_price': data['close_price'].iloc[-1] if 'close_price' in data.columns else None
                        })
                        print("✅ OK")
                    else:
                        results['test_tickers'].append({
                            'ticker': ticker,
                            'status': 'no_data',
                            'error': 'Нет данных'
                        })
                        print("❌ NO DATA")
                        
                except Exception as e:
                    results['test_tickers'].append({
                        'ticker': ticker,
                        'status': 'error',
                        'error': str(e)
                    })
                    print("❌ ERROR")
            
            end_time = datetime.now()
            results['response_time'] = (end_time - start_time).total_seconds()
            
            # Определяем доступность
            valid_tests = sum(1 for t in results['test_tickers'] if t['status'] == 'success')
            if valid_tests >= 3:  # Если хотя бы 3 из 5 тестов прошли
                results['moex_accessible'] = True
                print(f"\n✅ MOEX API доступен")
            else:
                print(f"\n❌ MOEX API недоступен или есть проблемы")
            
            print(f"⏱ Время ответа: {results['response_time']:.2f} сек")
            
            # Показываем результаты по тикерам
            print("\n📊 Результаты тестовых запросов:")
            for test in results['test_tickers']:
                status = "✅" if test['status'] == 'success' else "❌"
                price_info = f", цена: {test['last_price']:.2f}" if test.get('last_price') else ""
                print(f"  {status} {test['ticker']}: {test.get('data_points', 0)} записей{price_info}")
            
        except Exception as e:
            print(f"❌ Ошибка проверки подключения: {e}")
            results['error'] = str(e)
        
        return results
    
    def check_data_quality(self) -> Dict:
        """
        Проверяет качество исторических данных
        
        Returns:
            Словарь с результатами проверки
        """
        print("📊 Проверка качества данных...")
        
        results = {
            'checked_tickers': 0,
            'tickers_with_data': 0,
            'avg_data_points': 0,
            'quality_issues': [],
            'ticker_details': {}
        }
        
        try:
            # Загружаем несколько тикеров для проверки
            tickers = self.data_loader.load_tickers_from_db(stock_type=1)
            if not tickers:
                print("❌ Нет тикеров для проверки")
                return results
            
            # Берем случайную выборку
            import random
            sample_size = min(5, len(tickers))
            sample_tickers = random.sample(tickers, sample_size)
            
            total_data_points = 0
            
            for ticker_info in sample_tickers:
                ticker = ticker_info['ticker']
                print(f"  📈 {ticker}...", end=" ", flush=True)
                
                try:
                    # Получаем данные
                    data = self.data_loader.get_ticker_data(ticker, days=30)
                    
                    if data.empty:
                        results['quality_issues'].append(f"{ticker}: нет данных")
                        print("❌ НЕТ ДАННЫХ")
                    else:
                        results['tickers_with_data'] += 1
                        total_data_points += len(data)
                        
                        # Проверяем качество
                        issues = self._check_data_issues(data, ticker)
                        if issues:
                            results['quality_issues'].extend(issues)
                            print(f"⚠️ ЕСТЬ ПРОБЛЕМЫ ({len(data)} точек)")
                        else:
                            print(f"✅ OK ({len(data)} точек)")
                        
                        # Сохраняем детали
                        results['ticker_details'][ticker] = {
                            'data_points': len(data),
                            'date_range': {
                                'start': data['Date'].min().strftime('%Y-%m-%d') if not data.empty else None,
                                'end': data['Date'].max().strftime('%Y-%m-%d') if not data.empty else None
                            },
                            'avg_price': data['close_price'].mean() if not data.empty else None,
                            'issues': issues
                        }
                
                except Exception as e:
                    results['quality_issues'].append(f"{ticker}: ошибка загрузки - {str(e)}")
                    print("❌ ОШИБКА")
            
            results['checked_tickers'] = len(sample_tickers)
            
            # Рассчитываем среднее
            if results['tickers_with_data'] > 0:
                results['avg_data_points'] = total_data_points / results['tickers_with_data']
            
            # Выводим сводку
            print(f"\n📋 Сводка качества данных:")
            print(f"  📊 Проверено тикеров: {results['checked_tickers']}")
            print(f"  📈 С данными: {results['tickers_with_data']}")
            print(f"  📅 Среднее точек данных: {results['avg_data_points']:.1f}")
            
            if results['quality_issues']:
                print(f"  ⚠️  Проблемы качества: {len(results['quality_issues'])}")
                for issue in results['quality_issues'][:3]:  # Показываем первые 3
                    print(f"    • {issue}")
        
        except Exception as e:
            print(f"❌ Ошибка проверки качества данных: {e}")
        
        return results
    
    def _check_data_issues(self, data: pd.DataFrame, ticker: str) -> List[str]:
        """Проверяет данные на наличие проблем"""
        issues = []
        
        if data.empty:
            return [f"{ticker}: пустые данные"]
        
        # Проверяем пропущенные значения
        for column in ['close_price', 'open_price', 'high_price', 'low_price']:
            if column in data.columns:
                null_count = data[column].isnull().sum()
                if null_count > 0:
                    issues.append(f"{ticker}: {null_count} пропусков в {column}")
        
        # Проверяем нулевые или отрицательные цены
        if 'close_price' in data.columns:
            invalid_prices = data[data['close_price'] <= 0]
            if len(invalid_prices) > 0:
                issues.append(f"{ticker}: {len(invalid_prices)} невалидных цен")
        
        # Проверяем объем
        if 'volume' in data.columns:
            zero_volume = data[data['volume'] == 0]
            if len(zero_volume) > len(data) * 0.5:  # Если более 50% дней с нулевым объемом
                issues.append(f"{ticker}: много дней с нулевым объемом")
        
        # Проверяем даты на пропуски
        if 'Date' in data.columns and len(data) > 1:
            data_sorted = data.sort_values('Date')
            date_diff = data_sorted['Date'].diff().dt.days
            large_gaps = date_diff[date_diff > 5]  # Пропуски более 5 дней
            if len(large_gaps) > 0:
                issues.append(f"{ticker}: пропуски в датах")
        
        return issues
    
    def full_validation(self):
        """Выполняет полную проверку системы"""
        print("🔍 ПОЛНАЯ ПРОВЕРКА СИСТЕМЫ")
        print("═" * 60)
        
        all_results = {}
        
        try:
            # 1. Проверка базы данных
            print("\n1. 📁 Проверка базы данных...")
            db_results = self.check_database()
            all_results['database'] = db_results
            
            # 2. Проверка подключения к MOEX
            print("\n2. 🌐 Проверка подключения к MOEX...")
            moex_results = self.check_moex_connection()
            all_results['moex'] = moex_results
            
            # 3. Проверка тикеров (только если БД в порядке)
            if db_results.get('stocks_count', 0) > 0:
                print("\n3. 📊 Проверка тикеров...")
                ticker_results = self.check_tickers(sample_size=5)
                all_results['tickers'] = ticker_results
            else:
                print("\n3. ⏭️  Пропуск проверки тикеров (нет данных в БД)")
            
            # 4. Проверка качества данных
            print("\n4. 📈 Проверка качества данных...")
            quality_results = self.check_data_quality()
            all_results['quality'] = quality_results
            
            # Выводим общую сводку
            self._print_full_validation_summary(all_results)
            
        except Exception as e:
            print(f"\n❌ Ошибка полной проверки: {e}")
    
    def _print_full_validation_summary(self, results: Dict):
        """Выводит сводку полной проверки"""
        print("\n" + "═" * 60)
        print("📋 ОБЩАЯ СВОДКА ПРОВЕРКИ")
        print("═" * 60)
        
        # Оценка системы
        system_status = "✅ ГОТОВА К РАБОТЕ"
        issues_count = 0
        
        # Проверяем базу данных
        if 'database' in results:
            db = results['database']
            if not db.get('db_exists', False):
                system_status = "❌ КРИТИЧЕСКИЕ ПРОБЛЕМЫ"
                issues_count += 1
                print("❌ База данных не найдена")
            elif not db.get('tables_exist', False):
                print("⚠️  Не все таблицы существуют")
                issues_count += 1
            elif db.get('stocks_count', 0) == 0:
                print("⚠️  База данных пуста")
                issues_count += 1
            else:
                print(f"✅ База данных: {db.get('stocks_count', 0)} акций")
        
        # Проверяем MOEX
        if 'moex' in results:
            moex = results['moex']
            if not moex.get('moex_accessible', False):
                print("❌ Проблемы с подключением к MOEX")
                issues_count += 1
            else:
                print(f"✅ MOEX API: доступен ({moex.get('response_time', 0):.1f} сек)")
        
        # Проверяем тикеры
        if 'tickers' in results:
            tickers = results['tickers']
            if tickers.get('checked_tickers', 0) > 0:
                valid_percent = (tickers.get('valid_tickers', 0) / tickers.get('checked_tickers', 1)) * 100
                if valid_percent < 70:
                    print(f"⚠️  Тикеры: только {valid_percent:.1f}% валидных")
                    issues_count += 1
                else:
                    print(f"✅ Тикеры: {valid_percent:.1f}% валидных")
        
        # Проверяем качество данных
        if 'quality' in results:
            quality = results['quality']
            if quality.get('checked_tickers', 0) > 0:
                data_percent = (quality.get('tickers_with_data', 0) / quality.get('checked_tickers', 1)) * 100
                if data_percent < 50:
                    print(f"⚠️  Данные: только {data_percent:.1f}% тикеров с данными")
                    issues_count += 1
                else:
                    print(f"✅ Данные: {data_percent:.1f}% тикеров с данными")
        
        print("─" * 50)
        
        if issues_count == 0:
            print("🎉 Система полностью готова к работе!")
        elif issues_count == 1:
            print("⚠️  Найдена 1 проблема, система может работать")
        else:
            print(f"⚠️  Найдено {issues_count} проблем, требуется внимание")
        
        print("═" * 60)


def validate_single_ticker(ticker: str) -> Dict:
    """
    Проверяет один тикер
    
    Args:
        ticker: Тикер для проверки
    
    Returns:
        Словарь с результатами проверки
    """
    validator = DataValidator()
    
    results = {
        'ticker': ticker,
        'validation_steps': [],
        'is_valid': False,
        'issues': []
    }
    
    try:
        print(f"🔍 Проверка тикера {ticker}...")
        
        # Используем data_loader для проверки
        data = validator.data_loader.get_ticker_data(ticker, days=10)
        
        if data.empty:
            results['validation_steps'].append('Данные: ❌')
            results['issues'].append("Нет исторических данных")
            print(f"  ❌ Нет исторических данных")
            return results
        
        results['validation_steps'].append(f"Данные: ✅ ({len(data)} дней)")
        print(f"  ✅ Данные: {len(data)} дней")
        
        # Проверка качества данных
        issues = validator._check_data_issues(data, ticker)
        if issues:
            results['validation_steps'].append('Качество: ⚠️')
            results['issues'].extend(issues)
            print(f"  ⚠️  Проблемы качества: {len(issues)}")
        else:
            results['validation_steps'].append('Качество: ✅')
            print(f"  ✅ Качество данных: OK")
        
        # Проверка наличия в базе
        try:
            conn = sqlite3.connect(validator.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM stocks WHERE ticker = ?", (ticker,))
            db_result = cursor.fetchone()
            conn.close()
            
            if db_result:
                results['validation_steps'].append('База: ✅')
                print(f"  ✅ Найден в базе данных: {db_result[0]}")
            else:
                results['validation_steps'].append('База: ⚠️')
                results['issues'].append("Не найден в базе данных")
                print(f"  ⚠️  Не найден в базе данных")
        except:
            results['validation_steps'].append('База: ❌')
            results['issues'].append("Ошибка доступа к базе данных")
            print(f"  ❌ Ошибка доступа к базе")
        
        # Итоговая оценка
        if len(results['issues']) == 0:
            results['is_valid'] = True
            print(f"\n🎉 Тикер {ticker} полностью валиден!")
        else:
            print(f"\n⚠️  Тикер {ticker} имеет {len(results['issues'])} проблем")
        
        # Сохраняем детали
        results['data_points'] = len(data)
        results['last_price'] = float(data['close_price'].iloc[-1]) if not data.empty else None
        results['date_range'] = {
            'start': data['Date'].min().strftime('%Y-%m-%d') if not data.empty else None,
            'end': data['Date'].max().strftime('%Y-%m-%d') if not data.empty else None
        }
        
    except Exception as e:
        results['validation_steps'].append(f"Ошибка: {str(e)}")
        results['issues'].append(f"Критическая ошибка: {e}")
        print(f"❌ Критическая ошибка: {e}")
    
    return results


if __name__ == "__main__":
    # Пример использования
    validator = DataValidator()
    
    print("🔧 ВАЛИДАЦИЯ ДАННЫХ СИСТЕМЫ")
    print("═" * 60)
    
    # Быстрая проверка
    validator.full_validation()