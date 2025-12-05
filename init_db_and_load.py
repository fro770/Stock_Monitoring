"""
init_db_and_load.py
Скрипт для инициализации базы данных и загрузки данных из Excel/CSV файлов
"""
import sqlite3
import pandas as pd
import os
import sys
from datetime import datetime
import logging

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("logs/db_init.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Конфигурация
DATA_DIR = "data"
DB_NAME = "stocks.db"
EXCEL_FILE = os.path.join(DATA_DIR, "moex_all_shares.xlsx")
CSV_FILE = os.path.join(DATA_DIR, "moex_all_shares.csv")

def ensure_data_directory():
    """Создает папку data, если она не существует"""
    try:
        if not os.path.exists(DATA_DIR):
            os.makedirs(DATA_DIR)
            logger.info(f"Создана папка: {DATA_DIR}")
        return True
    except Exception as e:
        logger.error(f"Ошибка при создании папки {DATA_DIR}: {e}")
        return False

def create_database():
    """Создает базу данных SQLite и необходимые таблицы"""
    db_path = os.path.join(DATA_DIR, DB_NAME)
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Создаем таблицу для акций
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS stocks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            sectype TEXT,
            type_description TEXT,
            board TEXT DEFAULT 'TQBR',
            isin TEXT,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        
        # Создаем таблицу для истории цен (если понадобится в будущем)
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS price_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            date DATE NOT NULL,
            open REAL,
            high REAL,
            low REAL,
            close REAL,
            volume INTEGER,
            FOREIGN KEY (ticker) REFERENCES stocks (ticker),
            UNIQUE(ticker, date)
        )
        ''')
        
        # Создаем таблицу для мониторинга
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS monitoring (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            target_price REAL,
            is_active BOOLEAN DEFAULT 1,
            notification_email TEXT,
            last_notified TIMESTAMP,
            FOREIGN KEY (ticker) REFERENCES stocks (ticker)
        )
        ''')
        
        # Создаем таблицу для пользовательских заметок
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            note TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (ticker) REFERENCES stocks (ticker)
        )
        ''')
        
        # Создаем индексы для быстрого поиска
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_stocks_ticker ON stocks(ticker)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_stocks_sectype ON stocks(sectype)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_price_history_ticker_date ON price_history(ticker, date)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_monitoring_ticker ON monitoring(ticker)')
        
        conn.commit()
        logger.info(f"База данных создана: {db_path}")
        logger.info("Созданы таблицы: stocks, price_history, monitoring, notes")
        
        return conn
        
    except sqlite3.Error as e:
        logger.error(f"Ошибка SQLite при создании БД: {e}")
        return None
    except Exception as e:
        logger.error(f"Неожиданная ошибка при создании БД: {e}")
        return None

def load_data_from_excel(conn):
    """Загружает данные из Excel файла"""
    try:
        if not os.path.exists(EXCEL_FILE):
            logger.error(f"Файл Excel не найден: {EXCEL_FILE}")
            print(f"❌ Файл {EXCEL_FILE} не найден!")
            print("   Сначала запустите make_excel.py для создания файла с данными")
            return False
        
        logger.info(f"Чтение данных из Excel файла: {EXCEL_FILE}")
        
        # Читаем все листы из Excel
        excel_data = pd.read_excel(EXCEL_FILE, sheet_name=None)
        
        # Сначала загружаем все акции из основного листа
        if 'Все акции' in excel_data:
            df = excel_data['Все акции']
            logger.info(f"Найден лист 'Все акции' с {len(df)} записями")
        elif 'Акции' in excel_data:
            df = excel_data['Акции']
            logger.info(f"Найден лист 'Акции' с {len(df)} записями")
        else:
            # Берем первый лист
            first_sheet = list(excel_data.keys())[0]
            df = excel_data[first_sheet]
            logger.info(f"Найден лист '{first_sheet}' с {len(df)} записями")
        
        # Подготавливаем данные для вставки
        cursor = conn.cursor()
        
        # Очищаем таблицу перед загрузкой новых данных
        cursor.execute('DELETE FROM stocks')
        logger.info("Очищена таблица stocks")
        
        # Загружаем данные
        records_added = 0
        for _, row in df.iterrows():
            try:
                # Определяем тип акции на основе доступных колонок
                sectype = None
                type_description = None
                
                if 'Тип_акции' in row:
                    sectype = str(row['Тип_акции']) if pd.notna(row['Тип_акции']) else None
                elif 'SECTYPE' in row:
                    sectype = str(row['SECTYPE']) if pd.notna(row['SECTYPE']) else None
                
                if 'Тип_акции_расшифровка' in row:
                    type_description = str(row['Тип_акции_расшифровка']) if pd.notna(row['Тип_акции_расшифровка']) else None
                
                # Определяем тикер и название
                ticker = None
                name = None
                
                if 'Тикер' in row:
                    ticker = str(row['Тикер']) if pd.notna(row['Тикер']) else None
                elif 'SECID' in row:
                    ticker = str(row['SECID']) if pd.notna(row['SECID']) else None
                
                if 'Название' in row:
                    name = str(row['Название']) if pd.notna(row['Название']) else None
                elif 'SHORTNAME' in row:
                    name = str(row['SHORTNAME']) if pd.notna(row['SHORTNAME']) else None
                
                if ticker and name:
                    cursor.execute('''
                    INSERT OR REPLACE INTO stocks (ticker, name, sectype, type_description)
                    VALUES (?, ?, ?, ?)
                    ''', (ticker, name, sectype, type_description))
                    records_added += 1
                    
            except Exception as e:
                logger.warning(f"Ошибка при обработке строки: {row.to_dict()}, ошибка: {e}")
                continue
        
        conn.commit()
        logger.info(f"Добавлено {records_added} записей в таблицу stocks")
        
        # Загружаем отдельные листы для разных типов акций
        type_mapping = {
            'Обыкновенные акции': '1',
            'Привилегированные акции': '2'
        }
        
        for sheet_name, sectype_value in type_mapping.items():
            if sheet_name in excel_data:
                type_df = excel_data[sheet_name]
                logger.info(f"Обновление типа акций для листа '{sheet_name}' ({len(type_df)} записей)")
                
                for _, row in type_df.iterrows():
                    try:
                        ticker = None
                        if 'Тикер' in row:
                            ticker = str(row['Тикер']) if pd.notna(row['Тикер']) else None
                        elif 'SECID' in row:
                            ticker = str(row['SECID']) if pd.notna(row['SECID']) else None
                        
                        if ticker:
                            cursor.execute('''
                            UPDATE stocks 
                            SET sectype = ?, type_description = ?
                            WHERE ticker = ?
                            ''', (sectype_value, sheet_name, ticker))
                            
                    except Exception as e:
                        logger.warning(f"Ошибка при обновлении типа для тикера {ticker}: {e}")
        
        conn.commit()
        logger.info("Типы акций обновлены")
        
        return True
        
    except Exception as e:
        logger.error(f"Ошибка при загрузке данных из Excel: {e}")
        return False

def load_data_from_csv(conn):
    """Загружает данные из CSV файла (резервный вариант)"""
    try:
        if not os.path.exists(CSV_FILE):
            logger.error(f"CSV файл не найден: {CSV_FILE}")
            return False
        
        logger.info(f"Чтение данных из CSV файла: {CSV_FILE}")
        df = pd.read_csv(CSV_FILE, encoding='utf-8-sig')
        
        cursor = conn.cursor()
        cursor.execute('DELETE FROM stocks')
        
        records_added = 0
        for _, row in df.iterrows():
            try:
                ticker = str(row['Тикер']) if 'Тикер' in row and pd.notna(row['Тикер']) else None
                name = str(row['Название']) if 'Название' in row and pd.notna(row['Название']) else None
                sectype = str(row['Тип_акции']) if 'Тип_акции' in row and pd.notna(row['Тип_акции']) else None
                
                if ticker and name:
                    cursor.execute('''
                    INSERT OR REPLACE INTO stocks (ticker, name, sectype)
                    VALUES (?, ?, ?)
                    ''', (ticker, name, sectype))
                    records_added += 1
                    
            except Exception as e:
                logger.warning(f"Ошибка при обработке строки CSV: {e}")
                continue
        
        conn.commit()
        logger.info(f"Добавлено {records_added} записей из CSV")
        
        return True
        
    except Exception as e:
        logger.error(f"Ошибка при загрузке данных из CSV: {e}")
        return False

def verify_database(conn):
    """Проверяет целостность данных в базе"""
    try:
        cursor = conn.cursor()
        
        # Получаем статистику
        cursor.execute('SELECT COUNT(*) FROM stocks')
        total_stocks = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(DISTINCT ticker) FROM stocks')
        unique_tickers = cursor.fetchone()[0]
        
        cursor.execute('SELECT sectype, COUNT(*) FROM stocks GROUP BY sectype')
        type_stats = cursor.fetchall()
        
        logger.info("=" * 50)
        logger.info("ПРОВЕРКА БАЗЫ ДАННЫХ:")
        logger.info(f"Всего записей: {total_stocks}")
        logger.info(f"Уникальных тикеров: {unique_tickers}")
        
        for sectype, count in type_stats:
            type_desc = {
                '1': 'Обыкновенные акции',
                '2': 'Привилегированные акции',
                'D': 'Депозитарные расписки',
                None: 'Тип не указан'
            }.get(sectype, sectype)
            logger.info(f"  {type_desc}: {count}")
        
        # Выводим несколько примеров
        cursor.execute('SELECT ticker, name, sectype FROM stocks ORDER BY ticker LIMIT 10')
        sample_stocks = cursor.fetchall()
        
        logger.info("\nПримеры записей (первые 10):")
        for ticker, name, sectype in sample_stocks:
            logger.info(f"  {ticker}: {name} [{sectype}]")
        
        return total_stocks > 0
        
    except Exception as e:
        logger.error(f"Ошибка при проверке базы данных: {e}")
        return False

def create_sample_monitoring_entries(conn):
    """Создает тестовые записи для мониторинга"""
    try:
        cursor = conn.cursor()
        
        # Очищаем таблицу мониторинга
        cursor.execute('DELETE FROM monitoring')
        
        # Получаем несколько популярных акций для мониторинга
        sample_tickers = ['SBER', 'GAZP', 'LKOH', 'ROSN', 'VTBR', 'YNDX', 'POLY', 'GMKN']
        
        cursor.execute(f'''
        SELECT ticker FROM stocks 
        WHERE ticker IN ({','.join(['?' for _ in sample_tickers])})
        ''', sample_tickers)
        
        available_tickers = [row[0] for row in cursor.fetchall()]
        
        # Добавляем тестовые записи для мониторинга
        for i, ticker in enumerate(available_tickers[:5]):  # Первые 5
            target_price = 100.0 + i * 10  # Просто примерные цены
            cursor.execute('''
            INSERT INTO monitoring (ticker, target_price, is_active)
            VALUES (?, ?, 1)
            ''', (ticker, target_price))
        
        conn.commit()
        logger.info(f"Добавлено {len(available_tickers[:5])} тестовых записей для мониторинга")
        
        return True
        
    except Exception as e:
        logger.error(f"Ошибка при создании тестовых записей мониторинга: {e}")
        return False

def main():
    """Основная функция"""
    print("=" * 60)
    print("ИНИЦИАЛИЗАЦИЯ БАЗЫ ДАННЫХ И ЗАГРУЗКА ДАННЫХ")
    print("=" * 60)
    
    # Шаг 1: Создаем папку data
    print("📁 Шаг 1: Создание структуры папок...")
    if not ensure_data_directory():
        print("❌ Не удалось создать папку data")
        return
    
    # Шаг 2: Создаем базу данных
    print("🗄️  Шаг 2: Создание базы данных...")
    conn = create_database()
    if not conn:
        print("❌ Не удалось создать базу данных")
        return
    
    # Шаг 3: Загружаем данные из Excel
    print("📊 Шаг 3: Загрузка данных из Excel...")
    excel_loaded = load_data_from_excel(conn)
    
    # Шаг 4: Если Excel не загрузился, пробуем CSV
    if not excel_loaded:
        print("⚠️  Excel не загружен, пробуем CSV...")
        csv_loaded = load_data_from_csv(conn)
        if not csv_loaded:
            print("❌ Не удалось загрузить данные ни из Excel, ни из CSV")
            conn.close()
            return
    
    # Шаг 5: Проверяем базу данных
    print("🔍 Шаг 4: Проверка целостности данных...")
    db_ok = verify_database(conn)
    
    # Шаг 6: Создаем тестовые записи для мониторинга
    print("🎯 Шаг 5: Создание тестовых записей мониторинга...")
    create_sample_monitoring_entries(conn)
    
    # Шаг 7: Финальная проверка
    print("📋 Шаг 6: Финальная проверка...")
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM stocks')
    total_stocks = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM monitoring')
    total_monitoring = cursor.fetchone()[0]
    
    # Закрываем соединение
    conn.close()
    
    print("=" * 60)
    if total_stocks > 0:
        print(f"✅ БАЗА ДАННЫХ УСПЕШНО СОЗДАНА!")
        print(f"   📊 Всего акций: {total_stocks}")
        print(f"   🎯 Записей мониторинга: {total_monitoring}")
        print(f"   💾 Файл базы данных: {DATA_DIR}/{DB_NAME}")
        print("\n📋 Доступные таблицы:")
        print("   1. stocks - список всех акций")
        print("   2. price_history - история цен (пустая)")
        print("   3. monitoring - настройки мониторинга")
        print("   4. notes - пользовательские заметки")
        print("\n🔧 Для работы с базой данных используйте:")
        print("   - SQLite Browser (GUI)")
        print("   - Команду: sqlite3 data/stocks.db")
        print("   - Python скрипты с библиотекой sqlite3")
    else:
        print("❌ БАЗА ДАННЫХ СОЗДАНА, НО ДАННЫЕ НЕ ЗАГРУЖЕНЫ")
    
    print("=" * 60)

if __name__ == "__main__":
    # Проверяем наличие необходимых файлов
    if not os.path.exists(EXCEL_FILE) and not os.path.exists(CSV_FILE):
        print(f"⚠️  Внимание: ни один из файлов не найден:")
        print(f"   - {EXCEL_FILE}")
        print(f"   - {CSV_FILE}")
        print("\n   Сначала запустите make_excel.py для создания файла с данными")
        print("   Запустить скрипт все равно? (y/n): ", end="")
        response = input().strip().lower()
        if response != 'y':
            print("Отменено пользователем")
            sys.exit(1)
    
    # Запускаем основной процесс
    main()