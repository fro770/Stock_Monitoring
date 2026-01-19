"""
Главный скрипт системы анализа акций
Точка входа для запуска анализа акций MOEX
"""

import os
import sys
import logging
from datetime import datetime
import argparse
from colorama import Fore, Style, init as colorama_init
import numpy as np

# Добавляем путь к модулям
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

# Инициализация colorama
colorama_init(autoreset=True)

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("logs/analysis.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

from analysis.core.data_loader import DataLoader
from analysis.core.validator import DataValidator
from analysis.analyzer import StockAnalyzer
from analysis.reporter import ReportGenerator


def print_banner():
    """Печатает красивый баннер"""
    print(Fore.CYAN + "╔══════════════════════════════════════════════════════════════╗")
    print(Fore.CYAN + "║" + Fore.YELLOW + "         📊 СИСТЕМА АНАЛИЗА АКЦИЙ MOEX v1.0         " + Fore.CYAN + "║")
    print(Fore.CYAN + "╠══════════════════════════════════════════════════════════════╣")
    print(Fore.CYAN + "║" + Fore.WHITE + "  Машинное обучение + Технический анализ + Прогнозы  " + Fore.CYAN + "║")
    print(Fore.CYAN + "╚══════════════════════════════════════════════════════════════╝")
    print()


def print_menu():
    """Печатает меню выбора режима"""
    print(Fore.GREEN + "\n🔧 ВЫБЕРИТЕ РЕЖИМ РАБОТЫ:")
    print(Fore.GREEN + "─" * 50)
    print(Fore.WHITE + "  1. 📈 Анализ акций (полный цикл)")
    print(Fore.WHITE + "  2. 🔍 Проверка данных (валидация)")
    print(Fore.WHITE + "  3. 📥 Только загрузка тикеров")
    print(Fore.WHITE + "  4. 🚀 Быстрый анализ (топ-20)")
    print(Fore.WHITE + "  5. ⚙️  Настройки")
    print(Fore.WHITE + "  0. ❌ Выход")
    print(Fore.GREEN + "─" * 50)


def get_analysis_params():
    """Получает параметры анализа от пользователя"""
    print(Fore.CYAN + "\n⚙️  НАСТРОЙКИ АНАЛИЗА")
    print(Fore.CYAN + "─" * 50)
    
    params = {}
    
    # 1. Количество акций
    while True:
        try:
            top_n = input(Fore.WHITE + "🎯 Количество топ-акций для анализа (1-259, 'все'=259): ").strip()
            if top_n.lower() in ['все', 'all', '']:
                params['top_n'] = 259
                break
            else:
                top_n = int(top_n)
                if 1 <= top_n <= 259:
                    params['top_n'] = top_n
                    break
                else:
                    print(Fore.RED + "❌ Введите число от 1 до 259")
        except ValueError:
            print(Fore.RED + "❌ Введите число или 'все'")
    
    # 2. Тип акций
    print(Fore.WHITE + "\n📊 Выберите тип акций:")
    print(Fore.WHITE + "  1. Все акции")
    print(Fore.WHITE + "  2. Только обыкновенные")
    print(Fore.WHITE + "  3. Только привилегированные")
    
    while True:
        choice = input(Fore.WHITE + "Ваш выбор (1/2/3): ").strip()
        if choice in ['1', '2', '3']:
            params['stock_type'] = int(choice)
            break
        else:
            print(Fore.RED + "❌ Введите 1, 2 или 3")
    
    # 3. Режим анализа
    print(Fore.WHITE + "\n🚀 Выберите режим анализа:")
    print(Fore.WHITE + "  1. Быстрый (только тренды)")
    print(Fore.WHITE + "  2. Стандартный (ML + тренды)")
    print(Fore.WHITE + "  3. Глубокий (ансамбль моделей)")
    
    while True:
        choice = input(Fore.WHITE + "Ваш выбор (1/2/3): ").strip()
        if choice in ['1', '2', '3']:
            params['mode'] = int(choice)
            break
        else:
            print(Fore.RED + "❌ Введите 1, 2 или 3")
    
    # 4. Дни прогноза
    print(Fore.WHITE + "\n📅 Дни для прогноза (через запятую, например: 1,7,14,30):")
    while True:
        try:
            days_input = input(Fore.WHITE + "Введите дни: ").strip()
            if not days_input:
                params['prediction_days'] = [1, 7, 14, 30]
                break
            
            days = [int(d.strip()) for d in days_input.split(',')]
            if all(d > 0 for d in days):
                params['prediction_days'] = sorted(days)
                break
            else:
                print(Fore.RED + "❌ Все дни должны быть положительными")
        except:
            print(Fore.RED + "❌ Неверный формат. Пример: 1,7,14,30")
    
    # 5. Минимальная уверенность
    print(Fore.WHITE + "\n🎯 Минимальная уверенность моделей (1-100%):")
    print(Fore.WHITE + "   Пример: 50 = только прогнозы с уверенностью ≥50%")
    
    while True:
        try:
            confidence = input(Fore.WHITE + "Введите % (по умолчанию 50): ").strip()
            if not confidence:
                params['min_confidence'] = 0.5
                break
            
            confidence = float(confidence)
            if 0 <= confidence <= 100:
                params['min_confidence'] = confidence / 100
                break
            else:
                print(Fore.RED + "❌ Введите число от 0 до 100")
        except:
            print(Fore.RED + "❌ Введите число")
    
    return params


def print_analysis_summary(params):
    """Выводит сводку настроек анализа"""
    print(Fore.GREEN + "\n📋 СВОДКА НАСТРОЕК")
    print(Fore.GREEN + "─" * 50)
    
    stock_types = {
        1: "Все акции",
        2: "Только обыкновенные", 
        3: "Только привилегированные"
    }
    
    modes = {
        1: "Быстрый (тренды)",
        2: "Стандартный (ML)", 
        3: "Глубокий (ансамбль)"
    }
    
    print(Fore.WHITE + f"   🎯 Топ акций: {params['top_n']}")
    print(Fore.WHITE + f"   📊 Тип акций: {stock_types[params['stock_type']]}")
    print(Fore.WHITE + f"   🚀 Режим анализа: {modes[params['mode']]}")
    print(Fore.WHITE + f"   📅 Прогноз на дни: {params['prediction_days']}")
    print(Fore.WHITE + f"   🎯 Минимальная уверенность: {params['min_confidence']*100:.0f}%")
    print(Fore.GREEN + "─" * 50)


def run_analysis():
    """Запускает полный анализ акций"""
    print(Fore.CYAN + "\n🚀 ЗАПУСК ПОЛНОГО АНАЛИЗА")
    print(Fore.CYAN + "─" * 50)
    
    try:
        # Получаем параметры
        params = get_analysis_params()
        print_analysis_summary(params)
        
        # Подтверждение
        confirm = input(Fore.YELLOW + "\n⚠️  Начать анализ? (да/нет): ").strip().lower()
        if confirm not in ['да', 'д', 'yes', 'y']:
            print(Fore.YELLOW + "👋 Анализ отменен")
            return
        
        # Создаем анализатор
        print(Fore.GREEN + "\n🔄 Инициализация анализатора...")
        analyzer = StockAnalyzer(
            stock_type=params['stock_type'],
            mode=params['mode'],
            prediction_days=params['prediction_days'],
            min_confidence=params['min_confidence']
        )
        
        # Загружаем тикеры
        print(Fore.GREEN + "\n📥 Загрузка тикеров из базы данных...")
        tickers = analyzer.load_tickers()
        
        if not tickers:
            print(Fore.RED + "❌ Не удалось загрузить тикеры")
            return
        
        print(Fore.GREEN + f"✅ Загружено {len(tickers)} тикеров")
        
        # Показываем примеры тикеров
        print(Fore.CYAN + "\n📝 Примеры тикеров для анализа:")
        print(Fore.CYAN + "─" * 50)
        for i, ticker in enumerate(tickers[:5], 1):
            print(Fore.WHITE + f"{i}. {ticker['ticker']:6s} - {ticker['name'][:30]}")
        if len(tickers) > 5:
            print(Fore.WHITE + f"... и еще {len(tickers) - 5} тикеров")
        print(Fore.CYAN + "─" * 50)
        
        # Запускаем анализ
        print(Fore.GREEN + "\n🔍 Запуск анализа...")
        print(Fore.YELLOW + "   ⏱ Это может занять некоторое время...")
        
        start_time = datetime.now()
        
        results = analyzer.analyze_all(tickers)
        
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        print(Fore.GREEN + f"\n✅ Анализ завершен за {duration:.1f} сек")
        print(Fore.GREEN + f"   📊 Проанализировано: {len(results)} тикеров")
        
        if not results:
            print(Fore.YELLOW + "⚠️  Нет результатов для отчета")
            return
        
        # Фильтруем по уверенности
        filtered_results = analyzer.filter_by_confidence(results)
        print(Fore.GREEN + f"   🎯 С достаточной уверенностью: {len(filtered_results)} тикеров")
        
        if not filtered_results:
            print(Fore.YELLOW + "⚠️  Нет тикеров с достаточной уверенностью")
            print(Fore.YELLOW + "   Попробуйте снизить минимальную уверенность")
            return
        
        # Сортируем и берем топ-N
        filtered_results.sort(key=lambda x: x['avg_change_percent'], reverse=True)
        top_results = filtered_results[:params['top_n']]
        
        print(Fore.GREEN + f"   🏆 Топ-{len(top_results)} акций отобрано")
        
        # Генерируем отчеты
        print(Fore.GREEN + "\n📊 Генерация отчетов...")
        
        try:
            reporter = ReportGenerator(top_results, params)
            
            # Консольный отчет
            print(Fore.CYAN + "\n" + "═" * 60)
            print(Fore.CYAN + "📋 КОНСОЛЬНЫЙ ОТЧЕТ")
            print(Fore.CYAN + "═" * 60)
            reporter.print_console_report()
            
            # Excel отчет
            print(Fore.GREEN + "\n💾 Создание Excel отчета...")
            excel_path = reporter.generate_excel_report()
            
            # CSV отчет
            print(Fore.GREEN + "📊 Создание CSV отчета...")
            csv_path = reporter.generate_csv_report()
            
            # Выводим информацию о сохраненных файлах
            print(Fore.CYAN + "\n📁 СОХРАНЕННЫЕ ФАЙЛЫ:")
            print(Fore.CYAN + "─" * 50)
            
            reports_dir = Config.REPORTS_DIR
            print(Fore.WHITE + f"📁 Папка с отчетами: {Fore.CYAN}{reports_dir}")
            
            if excel_path:
                excel_name = os.path.basename(excel_path)
                file_size = os.path.getsize(excel_path) / 1024  # Размер в КБ
                print(Fore.WHITE + f"📄 Excel отчет: {Fore.GREEN}{excel_name}")
                print(Fore.WHITE + f"   Размер: {file_size:.1f} КБ")
                
            if csv_path:
                csv_name = os.path.basename(csv_path)
                print(Fore.WHITE + f"📊 CSV отчет:  {Fore.GREEN}{csv_name}")
            
            print(Fore.CYAN + "─" * 50)
            
            # Финальная статистика
            best_ticker = top_results[0]['ticker'] if top_results else "N/A"
            best_growth = top_results[0]['avg_change_percent'] if top_results else 0
            avg_growth = np.mean([r['avg_change_percent'] for r in top_results]) if top_results else 0
            positive_count = sum(1 for r in top_results if r['avg_change_percent'] > 0)
            
            print(Fore.CYAN + "\n📈 ФИНАЛЬНАЯ СТАТИСТИКА:")
            print(Fore.CYAN + "─" * 50)
            print(Fore.WHITE + f"   🏆 Лучший тикер: {Fore.GREEN}{best_ticker} ({best_growth:+.2f}%)")
            print(Fore.WHITE + f"   📊 Средний рост: {Fore.GREEN if avg_growth > 0 else Fore.RED}{avg_growth:+.2f}%")
            print(Fore.WHITE + f"   📈 Положительных: {Fore.GREEN}{positive_count}/{len(top_results)}")
            print(Fore.WHITE + f"   🎯 Уверенность: ≥{params['min_confidence']*100:.0f}%")
            print(Fore.WHITE + f"   📅 Дата анализа: {datetime.now().strftime('%d.%m.%Y %H:%M')}")
            print(Fore.CYAN + "─" * 50)
            
            # Предлагаем открыть файл
            if excel_path and os.path.exists(excel_path):
                open_excel = input(Fore.YELLOW + "\n📂 Открыть Excel отчет? (да/нет): ").strip().lower()
                if open_excel in ['да', 'д', 'yes', 'y']:
                    try:
                        os.startfile(excel_path)
                        print(Fore.GREEN + "✅ Excel отчет открыт")
                    except Exception as e:
                        print(Fore.YELLOW + f"⚠️  Не удалось открыть файл автоматически: {e}")
                        print(Fore.WHITE + f"   Откройте файл вручную: {excel_path}")
            
            # Рекомендации
            print(Fore.CYAN + "\n💡 РЕКОМЕНДАЦИИ:")
            print(Fore.CYAN + "─" * 50)
            if avg_growth > 5:
                print(Fore.GREEN + "   📈 Сильный положительный тренд! Благоприятное время для инвестиций.")
            elif avg_growth > 0:
                print(Fore.CYAN + "   ↗️  Умеренный рост. Рассмотрите диверсификацию портфеля.")
            elif avg_growth < -5:
                print(Fore.RED + "   📉 Сильный отрицательный тренд. Будьте осторожны с инвестициями.")
            else:
                print(Fore.YELLOW + "   ⚖️  Нейтральный рынок. Требуется дополнительный анализ.")
            
            if positive_count > len(top_results) * 0.7:
                print(Fore.GREEN + "   ✅ Большинство прогнозов положительные")
            elif positive_count < len(top_results) * 0.3:
                print(Fore.RED + "   ⚠️  Большинство прогнозов отрицательные")
            else:
                print(Fore.YELLOW + "   ⚖️  Смешанные прогнозы")
            
            print(Fore.CYAN + "─" * 50)
            
        except Exception as e:
            print(Fore.RED + f"\n❌ Ошибка генерации отчетов: {e}")
            import traceback
            traceback.print_exc()
            
            # Пробуем простой вывод результатов
            print(Fore.YELLOW + "\n📋 ПРОСТЫЕ РЕЗУЛЬТАТЫ:")
            print(Fore.YELLOW + "─" * 50)
            for i, result in enumerate(top_results[:10], 1):
                growth_color = Fore.GREEN if result['avg_change_percent'] > 0 else Fore.RED if result['avg_change_percent'] < 0 else Fore.YELLOW
                print(Fore.WHITE + f"{i}. {result['ticker']:6s} - {result['name'][:20]}")
                print(f"   Рост: {growth_color}{result['avg_change_percent']:+.2f}%  Уверенность: {result['avg_confidence']*100:.1f}%  Цена: {result['last_price']:.2f}")
        
    except KeyboardInterrupt:
        print(Fore.YELLOW + "\n\n👋 Анализ прерван пользователем")
    except Exception as e:
        logger.error(f"Ошибка анализа: {e}", exc_info=True)
        print(Fore.RED + f"\n❌ Ошибка анализа: {e}")
        import traceback
        traceback.print_exc()


def run_validation():
    """Запускает проверку данных"""
    print(Fore.CYAN + "\n🔍 ПРОВЕРКА ДАННЫХ")
    print(Fore.CYAN + "─" * 50)
    
    try:
        validator = DataValidator()
        
        print(Fore.WHITE + "Выберите проверку:")
        print(Fore.WHITE + "  1. Проверить базу данных")
        print(Fore.WHITE + "  2. Проверить тикеры")
        print(Fore.WHITE + "  3. Проверить данные с MOEX")
        print(Fore.WHITE + "  4. Полная проверка")
        
        choice = input(Fore.WHITE + "Ваш выбор (1-4): ").strip()
        
        if choice == '1':
            validator.check_database()
        elif choice == '2':
            validator.check_tickers()
        elif choice == '3':
            validator.check_moex_connection()
        elif choice == '4':
            validator.full_validation()
        else:
            print(Fore.RED + "❌ Неверный выбор")
            
    except Exception as e:
        print(Fore.RED + f"❌ Ошибка проверки: {e}")


def run_quick_analysis():
    """Запускает быстрый анализ (топ-20)"""
    print(Fore.CYAN + "\n🚀 БЫСТРЫЙ АНАЛИЗ (ТОП-20)")
    print(Fore.CYAN + "─" * 50)
    
    try:
        # Используем параметры по умолчанию
        params = {
            'top_n': 20,
            'stock_type': 1,  # Все акции
            'mode': 1,        # Быстрый режим
            'prediction_days': [7, 14, 30],
            'min_confidence': 0.5
        }
        
        print(Fore.GREEN + "Параметры по умолчанию:")
        print_analysis_summary(params)
        
        confirm = input(Fore.YELLOW + "\n⚠️  Начать быстрый анализ? (да/нет): ").strip().lower()
        if confirm not in ['да', 'д', 'yes', 'y']:
            return
        
        # Упрощенный анализ
        data_loader = DataLoader()
        tickers = data_loader.load_tickers_from_db(stock_type=params['stock_type'])
        
        if not tickers:
            print(Fore.RED + "❌ Не удалось загрузить тикеры")
            return
        
        print(Fore.GREEN + f"✅ Загружено {len(tickers)} тикеров")
        
        # Проверяем только топ-20 по объему (упрощенно)
        print(Fore.GREEN + "\n🔍 Проверка данных...")
        
        valid_tickers = []
        for i, ticker_info in enumerate(tickers[:50]):  # Проверяем первые 50
            ticker = ticker_info['ticker']
            print(f"  {i+1:2d}. {ticker}...", end=" ", flush=True)
            
            try:
                data = data_loader.get_ticker_data(ticker, days=30)
                if not data.empty and len(data) >= 20:
                    valid_tickers.append(ticker_info)
                    print(Fore.GREEN + "OK")
                else:
                    print(Fore.YELLOW + "мало данных")
            except:
                print(Fore.RED + "ошибка")
        
        print(Fore.GREEN + f"\n✅ Найдено {len(valid_tickers)} тикеров с данными")
        
        # Простой анализ
        print(Fore.GREEN + "\n📈 Простой анализ...")
        results = []
        
        for ticker_info in valid_tickers[:20]:  # Берем только 20
            ticker = ticker_info['ticker']
            data = data_loader.get_ticker_data(ticker, days=60)
            
            if not data.empty:
                last_price = data['close_price'].iloc[-1]
                # Простой тренд (разница последней и первой цены)
                if len(data) >= 10:
                    first_price = data['close_price'].iloc[0]
                    change = ((last_price - first_price) / first_price) * 100
                    
                    results.append({
                        'ticker': ticker,
                        'name': ticker_info['name'],
                        'last_price': round(last_price, 2),
                        'change_percent': round(change, 2),
                        'data_points': len(data)
                    })
        
        # Сортируем по росту
        results.sort(key=lambda x: x['change_percent'], reverse=True)
        
        # Выводим результаты
        print(Fore.CYAN + "\n" + "═" * 60)
        print(Fore.CYAN + "📊 РЕЗУЛЬТАТЫ БЫСТРОГО АНАЛИЗА")
        print(Fore.CYAN + "═" * 60)
        
        for i, result in enumerate(results[:10], 1):
            color = Fore.GREEN if result['change_percent'] > 0 else Fore.RED
            print(f"{i:2d}. {result['ticker']:6s} - {result['name'][:30]:30s}")
            print(f"    Цена: {result['last_price']:8.2f}  Изменение: {color}{result['change_percent']:+.2f}%{Fore.RESET}")
        
        print(Fore.CYAN + "═" * 60)
        
    except Exception as e:
        print(Fore.RED + f"❌ Ошибка быстрого анализа: {e}")


def run_ticker_loading():
    """Загружает только тикеры"""
    print(Fore.CYAN + "\n📥 ЗАГРУЗКА ТИКЕРОВ")
    print(Fore.CYAN + "─" * 50)
    
    try:
        data_loader = DataLoader()
        
        print(Fore.WHITE + "Выберите тип акций:")
        print(Fore.WHITE + "  1. Все акции")
        print(Fore.WHITE + "  2. Только обыкновенные")
        print(Fore.WHITE + "  3. Только привилегированные")
        
        choice = input(Fore.WHITE + "Ваш выбор (1-3): ").strip()
        
        if choice in ['1', '2', '3']:
            stock_type = int(choice)
            tickers = data_loader.load_tickers_from_db(stock_type=stock_type)
            
            print(Fore.GREEN + f"\n✅ Загружено {len(tickers)} тикеров")
            
            # Показываем первые 10
            print(Fore.WHITE + "\nПервые 10 тикеров:")
            for i, ticker in enumerate(tickers[:10], 1):
                print(f"{i:2d}. {ticker['ticker']:6s} - {ticker['name'][:40]}")
            
            # Сохраняем в файл
            save = input(Fore.YELLOW + "\n💾 Сохранить в файл? (да/нет): ").strip().lower()
            if save in ['да', 'д', 'yes', 'y']:
                import pandas as pd
                df = pd.DataFrame(tickers)
                filename = f"tickers_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
                df.to_csv(filename, index=False, encoding='utf-8')
                print(Fore.GREEN + f"✅ Сохранено в {filename}")
        else:
            print(Fore.RED + "❌ Неверный выбор")
            
    except Exception as e:
        print(Fore.RED + f"❌ Ошибка загрузки: {e}")


def show_settings():
    """Показывает настройки системы"""
    print(Fore.CYAN + "\n⚙️  НАСТРОЙКИ СИСТЕМЫ")
    print(Fore.CYAN + "─" * 50)
    
    try:
        from analysis.core.config import Config
        
        print(Fore.WHITE + "Пути:")
        print(Fore.WHITE + f"  📁 База данных: {Config.DB_PATH}")
        print(Fore.WHITE + f"  📊 Отчеты: {Config.REPORTS_DIR}")
        print(Fore.WHITE + f"  📝 Логи: {Config.LOGS_DIR}")
        print(Fore.WHITE + f"  🧠 Модели: {Config.MODELS_DIR}")
        
        print(Fore.WHITE + "\nAPI:")
        print(Fore.WHITE + f"  🔗 MOEX: {Config.MOEX_BASE_URL}")
        print(Fore.WHITE + f"  ⏱ Таймаут: {Config.MOEX_TIMEOUT} сек")
        print(Fore.WHITE + f"  🔄 Повторы: {Config.MOEX_MAX_RETRIES}")
        
        print(Fore.WHITE + "\nАнализ:")
        print(Fore.WHITE + f"  📅 Дней истории: {Config.DEFAULT_HISTORY_DAYS}")
        print(Fore.WHITE + f"  👷‍♂️ Потоков: {Config.MAX_WORKERS}")
        
        # Проверяем существование файлов
        print(Fore.WHITE + "\nПроверка файлов:")
        files_to_check = [
            (Config.DB_PATH, "База данных"),
            (os.path.join(Config.MODELS_DIR, "finrl_output"), "FinRL модель"),
        ]
        
        for filepath, description in files_to_check:
            if os.path.exists(filepath):
                print(Fore.GREEN + f"  ✅ {description}: найдено")
            else:
                print(Fore.YELLOW + f"  ⚠️  {description}: не найдено")
                
    except Exception as e:
        print(Fore.RED + f"❌ Ошибка: {e}")


def main():
    """Главная функция"""
    print_banner()
    
    while True:
        try:
            print_menu()
            
            choice = input(Fore.YELLOW + "🎯 Ваш выбор (0-5): ").strip()
            
            if choice == '0':
                print(Fore.CYAN + "\n👋 До свидания!")
                break
            elif choice == '1':
                run_analysis()
            elif choice == '2':
                run_validation()
            elif choice == '3':
                run_ticker_loading()
            elif choice == '4':
                run_quick_analysis()
            elif choice == '5':
                show_settings()
            else:
                print(Fore.RED + "❌ Неверный выбор. Попробуйте снова.")
            
            print()  # Пустая строка для разделения
            
        except KeyboardInterrupt:
            print(Fore.YELLOW + "\n👋 До свидания!")
            break
        except Exception as e:
            logger.error(f"Ошибка в главном меню: {e}", exc_info=True)
            print(Fore.RED + f"\n❌ Неожиданная ошибка: {e}")


import os

# Добавляем корень проекта в путь
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Запускаем главный модуль
from analysis.main import main

if __name__ == "__main__":
    # Проверяем наличие необходимых директорий
    try:
        from analysis.core.config import Config
        Config.ensure_directories()
    except:
        pass
    
    # Запускаем главное меню
    main()