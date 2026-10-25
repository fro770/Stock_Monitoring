"""
Менеджер базы данных: создание схемы, загрузка списка акций из MOEX ISS API.

Заменяет собой устаревший init_db_and_load.py (который зависел от ручного
файла moex_all_shares.xlsx). Теперь список тикеров загружается напрямую
из API MOEX — первый запуск не требует никаких дополнительных файлов.
"""

import logging
import sqlite3
from datetime import datetime
from typing import Optional

from .config import Config
from .moex_client import WorkingMOEXClient

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Создание и наполнение базы данных проекта."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or Config.DB_PATH
        self.client = WorkingMOEXClient()

    # --- Схема ---------------------------------------------------------------

    def connect(self) -> sqlite3.Connection:
        Config.ensure_directories()
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def create_schema(self) -> None:
        """Создаёт таблицы, если их ещё нет (идемпотентно)."""
        conn = self.connect()
        try:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS stocks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticker TEXT UNIQUE NOT NULL,
                    name TEXT,
                    sectype TEXT,
                    type_description TEXT,
                    board TEXT,
                    isin TEXT,
                    last_updated TEXT,
                    created_at TEXT DEFAULT (datetime('now'))
                );

                CREATE TABLE IF NOT EXISTS price_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticker TEXT NOT NULL,
                    date TEXT NOT NULL,
                    open REAL, high REAL, low REAL, close REAL,
                    volume INTEGER,
                    UNIQUE(ticker, date)
                );

                CREATE INDEX IF NOT EXISTS idx_price_history_ticker_date
                    ON price_history(ticker, date);

                CREATE TABLE IF NOT EXISTS monitoring (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticker TEXT NOT NULL,
                    target_price REAL,
                    is_active INTEGER DEFAULT 1,
                    created_at TEXT DEFAULT (datetime('now'))
                );

                CREATE TABLE IF NOT EXISTS notes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticker TEXT,
                    note TEXT,
                    created_at TEXT DEFAULT (datetime('now'))
                );
                """
            )
            conn.commit()
        finally:
            conn.close()

    # --- Загрузка тикеров ----------------------------------------------------

    @staticmethod
    def _sectype_description(sectype: str) -> str:
        return {
            "1": "Обыкновенная акция",
            "2": "Привилегированная акция",
        }.get(str(sectype), "Акция")

    def load_tickers_from_moex(self, limit: Optional[int] = None) -> int:
        """Загружает список всех акций MOEX через ISS API и сохраняет в БД.

        Returns:
            Количество сохранённых тикеров.
        """
        logger.info("Загрузка списка акций с MOEX ISS API...")
        tickers = self.client.get_available_tickers(limit=limit or 1000)

        if not tickers:
            raise RuntimeError(
                "Не удалось получить список акций с MOEX. "
                "Проверьте подключение к интернету."
            )

        conn = self.connect()
        try:
            now = datetime.now().isoformat(timespec="seconds")
            saved = 0
            for t in tickers:
                ticker = (t.get("ticker") or "").strip()
                if not ticker:
                    continue
                try:
                    conn.execute(
                        """
                        INSERT INTO stocks (ticker, name, sectype, type_description,
                                            board, isin, last_updated)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(ticker) DO UPDATE SET
                            name = excluded.name,
                            sectype = excluded.sectype,
                            type_description = excluded.type_description,
                            board = excluded.board,
                            isin = excluded.isin,
                            last_updated = excluded.last_updated
                        """,
                        (
                            ticker,
                            t.get("name", ""),
                            str(t.get("sectype", "")),
                            self._sectype_description(t.get("sectype")),
                            t.get("board", "TQBR"),
                            t.get("isin", ""),
                            now,
                        ),
                    )
                    saved += 1
                except sqlite3.Error as e:
                    logger.warning("Пропущен тикер %s: %s", ticker, e)
            conn.commit()
        finally:
            conn.close()

        logger.info("Сохранено тикеров: %d", saved)
        return saved

    # --- Статистика ----------------------------------------------------------

    def get_stats(self) -> dict:
        stats = {"exists": False, "stocks": 0, "price_history": 0, "tickers_with_history": 0}
        import os
        if not os.path.exists(self.db_path):
            return stats
        stats["exists"] = True
        conn = sqlite3.connect(self.db_path, timeout=15)
        try:
            for table in ("stocks", "price_history"):
                try:
                    stats[table] = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                except sqlite3.Error:
                    stats[table] = 0
            try:
                stats["tickers_with_history"] = conn.execute(
                    "SELECT COUNT(DISTINCT ticker) FROM price_history"
                ).fetchone()[0]
            except sqlite3.Error:
                pass
        finally:
            conn.close()
        return stats

    def init_first_run(self, progress_cb=None) -> dict:
        """Полная инициализация при первом запуске: схема + тикеры из MOEX.

        Args:
            progress_cb: необязательная callback(status: str) для UI.

        Returns:
            Статистика БД после инициализации.
        """

        def report(msg: str):
            logger.info(msg)
            if progress_cb:
                try:
                    progress_cb(msg)
                except Exception:
                    pass

        report("Создание структуры базы данных...")
        self.create_schema()

        report("Загрузка списка акций с MOEX ISS API...")
        count = self.load_tickers_from_moex()
        report(f"Загружено тикеров: {count}")

        return self.get_stats()
