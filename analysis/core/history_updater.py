"""
Обновление истории котировок в базе данных (price_history).

Раньше эту функцию выполнял data/stock_data_fetcher.py (отсутствовал в git)
и корневой скрипт update_data.py. Логика перенесена сюда как единый
 serviced-метод, используемый и GUI, и CLI.
"""

import logging
import sqlite3
from datetime import datetime
from typing import Callable, List, Optional

import pandas as pd

from .config import Config
from .moex_client import WorkingMOEXClient

logger = logging.getLogger(__name__)


class PriceHistoryUpdater:
    """Загружает историю цен с MOEX и сохраняет в таблицу price_history."""

    def __init__(self):
        self.client = WorkingMOEXClient()
        self.db_path = Config.DB_PATH

    def _get_tickers(self, tickers: Optional[List[str]]) -> List[dict]:
        conn = sqlite3.connect(self.db_path, timeout=15)
        try:
            if tickers:
                placeholders = ",".join("?" * len(tickers))
                rows = conn.execute(
                    f"SELECT ticker, name FROM stocks WHERE ticker IN ({placeholders})",
                    tickers,
                ).fetchall()
            else:
                rows = conn.execute("SELECT ticker, name FROM stocks ORDER BY ticker").fetchall()
        finally:
            conn.close()
        return [{"ticker": r[0], "name": r[1] or r[0]} for r in rows]

    def update_one(self, ticker: str, days: int) -> int:
        """Загружает историю для одного тикера. Возвращает число сохранённых записей."""
        df = self.client.get_price_history(ticker, days)
        if df is None or df.empty:
            return 0
        return self._save_history(ticker, df)

    def _save_history(self, ticker: str, df: pd.DataFrame) -> int:
        # Ожидаем колонки Date / open / high / low / close_price / volume
        if "Date" not in df.columns or "close_price" not in df.columns:
            return 0
        rows = []
        for _, r in df.iterrows():
            date_val = r["Date"]
            date_str = date_val.strftime("%Y-%m-%d") if hasattr(date_val, "strftime") else str(date_val)[:10]
            rows.append((
                ticker, date_str,
                float(r.get("open_price") or r.get("open") or 0) or None,
                float(r.get("high_price") or r.get("high") or 0) or None,
                float(r.get("low_price") or r.get("low") or 0) or None,
                float(r.get("close_price") or r.get("close") or 0) or None,
                int(r.get("volume") or 0) or None,
            ))
        conn = sqlite3.connect(self.db_path, timeout=30)
        try:
            conn.executemany(
                """
                INSERT INTO price_history (ticker, date, open, high, low, close, volume)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(ticker, date) DO UPDATE SET
                    open = excluded.open, high = excluded.high, low = excluded.low,
                    close = excluded.close, volume = excluded.volume
                """,
                rows,
            )
            conn.commit()
        finally:
            conn.close()
        return len(rows)

    def update_all(
        self,
        tickers: Optional[List[str]] = None,
        days: int = None,
        progress_cb: Optional[Callable[[int, int, str], None]] = None,
        cancel_cb: Optional[Callable[[], bool]] = None,
    ) -> dict:
        """Пакетное обновление истории котировок.

        Args:
            tickers: список тикеров (None = все из таблицы stocks)
            days: глубина истории в днях (None = Config.DEFAULT_HISTORY_DAYS)
            progress_cb: callback(index, total, message) для UI
            cancel_cb: callback -> True, если пользователь нажал «Отмена»

        Returns:
            {'updated': int, 'skipped': int, 'records': int, 'errors': [str]}
        """
        days = days or Config.DEFAULT_HISTORY_DAYS
        items = self._get_tickers(tickers)
        result = {"updated": 0, "skipped": 0, "records": 0, "errors": []}

        total = len(items)
        for i, item in enumerate(items, 1):
            if cancel_cb and cancel_cb():
                logger.info("Обновление прервано пользователем на %d/%d", i - 1, total)
                break

            ticker = item["ticker"]
            if progress_cb:
                progress_cb(i, total, f"Обновление {ticker} ({i}/{total})...")
            try:
                n = self.update_one(ticker, days)
                if n > 0:
                    result["updated"] += 1
                    result["records"] += n
                else:
                    result["skipped"] += 1
            except Exception as e:
                result["errors"].append(f"{ticker}: {e}")
                logger.warning("Ошибка обновления %s: %s", ticker, e)

        logger.info(
            "Обновление завершено: %d тикеров, %d записей, %d пропущено, %d ошибок",
            result["updated"], result["records"], result["skipped"], len(result["errors"]),
        )
        return result
