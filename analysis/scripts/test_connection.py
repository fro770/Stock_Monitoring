#!/usr/bin/env python
"""
Полный тест системы
"""

import sys
import os

# Добавляем путь к модулям (скрипт лежит в analysis/scripts/)
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
for p in (project_root, current_dir):
    if p not in sys.path:
        sys.path.insert(0, p)
os.chdir(project_root)

import pandas as pd
from colorama import Fore, Style, init as colorama_init

colorama_init(autoreset=True)

def test_data_loader():
    """Тестирует DataLoader"""
    print(Fore.CYAN + "\n🧪 ТЕСТ DATA LOADER")
    print(Fore.CYAN + "─" * 50)
    
    try:
        from analysis.core.data_loader import DataLoader
        
        loader = DataLoader()
        
        # 1. Тест загрузки тикеров
        print(Fore.WHITE + "1. Загрузка тикеров из базы данных...")
        tickers = loader.load_tickers_from_db()
        
        if not tickers:
            print(Fore.RED + "   ❌ Не удалось загрузить тикеры")
            return False
        
        print(Fore.GREEN + f"   ✅ Загружено {len(tickers)} тикеров")
        
        # Показываем примеры
        print(Fore.WHITE + "   Примеры тикеров:")
        for i, ticker in enumerate(tickers[:5], 1):
            print(Fore.WHITE + f"     {i}. {ticker['ticker']} - {ticker['name']}")
        
        # 2. Быстрый тест данных
        print(Fore.WHITE + "\n2. Быстрый тест загрузки данных...")
        success = loader.quick_test(count=5)
        
        if not success:
            print(Fore.YELLOW + "   ⚠️  Быстрый тест не прошел")
        
        return True
        
    except Exception as e:
        print(Fore.RED + f"   ❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_moex_client_direct():
    """Прямой тест MOEX клиента"""
    print(Fore.CYAN + "\n🌐 ПРЯМОЙ ТЕСТ MOEX CLIENT")
    print(Fore.CYAN + "─" * 50)
    
    try:
        from analysis.core.moex_client import WorkingMOEXClient
        
        client = WorkingMOEXClient()
        
        # Тестируем популярные тикеры
        test_tickers = ['SBER', 'GAZP', 'LKOH', 'VTBR', 'YNDX']
        
        for ticker in test_tickers:
            print(Fore.WHITE + f"\n📊 {ticker}:")
            
            try:
                # Получаем данные
                data = client.get_price_history(ticker, days=10)
                
                if data.empty:
                    print(Fore.RED + f"   ❌ Нет данных")
                else:
                    print(Fore.GREEN + f"   ✅ Данные: {len(data)} записей")
                    print(Fore.WHITE + f"      Период: {data['Date'].min().date()} - {data['Date'].max().date()}")
                    print(Fore.WHITE + f"      Цена: {data['close_price'].iloc[-1]:.2f}")
                    
            except Exception as e:
                print(Fore.RED + f"   ❌ Ошибка: {e}")
        
        return True
        
    except Exception as e:
        print(Fore.RED + f"   ❌ Ошибка импорта: {e}")
        return False

def test_database():
    """Тестирует базу данных"""
    print(Fore.CYAN + "\n🗄️  ТЕСТ БАЗЫ ДАННЫХ")
    print(Fore.CYAN + "─" * 50)
    
    try:
        import sqlite3
        from analysis.core.config import Config
        
        db_path = Config.DB_PATH
        
        if not os.path.exists(db_path):
            print(Fore.RED + f"   ❌ База данных не найдена: {db_path}")
            return False
        
        print(Fore.GREEN + f"   ✅ База данных найдена: {db_path}")
        
        # Подключаемся к базе
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Проверяем таблицы
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]
        
        print(Fore.WHITE + f"   📊 Таблицы в базе: {len(tables)}")
        for table in tables:
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            count = cursor.fetchone()[0]
            print(Fore.WHITE + f"      • {table}: {count} записей")
        
        # Проверяем stocks таблицу
        if 'stocks' in tables:
            cursor.execute("SELECT ticker, name FROM stocks LIMIT 5")
            stocks = cursor.fetchall()
            
            print(Fore.WHITE + "\n   📝 Примеры акций:")
            for ticker, name in stocks:
                print(Fore.WHITE + f"      • {ticker} - {name}")
        
        conn.close()
        
        return True
        
    except Exception as e:
        print(Fore.RED + f"   ❌ Ошибка: {e}")
        return False

def main():
    print(Fore.YELLOW + "=" * 60)
    print(Fore.YELLOW + "🧪 ПОЛНЫЙ ТЕСТ СИСТЕМЫ АНАЛИЗА АКЦИЙ")
    print(Fore.YELLOW + "=" * 60)
    
    tests = [
        ("База данных", test_database),
        ("MOEX Клиент", test_moex_client_direct),
        ("Data Loader", test_data_loader),
    ]
    
    results = []
    
    for test_name, test_func in tests:
        print(Fore.CYAN + f"\n[{test_name.upper()}]")
        try:
            success = test_func()
            results.append((test_name, success))
        except Exception as e:
            print(Fore.RED + f"   ❌ Критическая ошибка: {e}")
            results.append((test_name, False))
    
    # Вывод итогов
    print(Fore.CYAN + "\n" + "=" * 60)
    print(Fore.CYAN + "📋 ИТОГИ ТЕСТИРОВАНИЯ")
    print(Fore.CYAN + "=" * 60)
    
    for test_name, success in results:
        status = Fore.GREEN + "✅ ПРОЙДЕН" if success else Fore.RED + "❌ ПРОВАЛЕН"
        print(Fore.WHITE + f"   {test_name}: {status}")
    
    passed = sum(1 for _, success in results if success)
    total = len(results)
    
    print(Fore.CYAN + "\n" + "=" * 60)
    if passed == total:
        print(Fore.GREEN + f"🎉 ВСЕ ТЕСТЫ ПРОЙДЕНЫ УСПЕШНО! ({passed}/{total})")
        print(Fore.GREEN + "   Система готова к работе!")
    elif passed >= total // 2:
        print(Fore.YELLOW + f"⚠️  ЧАСТИЧНЫЙ УСПЕХ ({passed}/{total})")
        print(Fore.YELLOW + "   Система может работать с ограничениями")
    else:
        print(Fore.RED + f"❌ МНОГО ОШИБОК ({passed}/{total})")
        print(Fore.RED + "   Требуется отладка системы")
    
    print(Fore.CYAN + "=" * 60)
    
    # Рекомендации
    if passed < total:
        print(Fore.YELLOW + "\n📋 РЕКОМЕНДАЦИИ:")
        print(Fore.YELLOW + "─" * 50)
        
        if not any("База данных" in name and success for name, success in results):
            print(Fore.WHITE + "1. Проверьте файл базы данных:")
            print(Fore.WHITE + "   - Существует ли data/stocks.db?")
            print(Fore.WHITE + "   - Запустите init_db_and_load.py для создания БД")
        
        if not any("MOEX Клиент" in name and success for name, success in results):
            print(Fore.WHITE + "\n2. Проблемы с MOEX API:")
            print(Fore.WHITE + "   - Проверьте интернет-подключение")
            print(Fore.WHITE + "   - Попробуйте открыть в браузере:")
            print(Fore.WHITE + "     https://iss.moex.com/iss/engines/stock/markets/shares/securities/SBER/candles.json")
        
        if not any("Data Loader" in name and success for name, success in results):
            print(Fore.WHITE + "\n3. Проблемы с загрузкой данных:")
            print(Fore.WHITE + "   - Проверьте импорт модулей")
            print(Fore.WHITE + "   - Убедитесь, что все зависимости установлены")
            print(Fore.WHITE + "   - Запустите: pip install -r requirements.txt")

if __name__ == "__main__":
    main()