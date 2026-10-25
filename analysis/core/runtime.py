"""
Единая точка конфигурации путей проекта (архитектура v2)

Все пути определяются от корня проекта, а не от текущей рабочей директории.
Корень проекта определяется автоматически по расположению этого файла:
    <root>/analysis/core/runtime.py  ->  root = parents[2]

Структура проекта:
    <root>/
    ├── main.py / launcher.py        - точки входа
    ├── analysis/                    - весь код анализа (пакет)
    │   ├── core/                    - ядро (загрузка, анализ, ML, отчёты, runtime)
    │   ├── models/                  - ML-модели (XGBoost/LightGBM/CatBoost)
    │   ├── scripts/                 - служебные скрипты ( formerly в корне)
    │   └── ui/                      - графический интерфейс
    ├── data/                        - база данных и кэш моделей
    ├── reports/                     - сгенерированные отчёты
    ├── logs/                        - логи
    └── weights/                     - веса LLM-моделей (не в git)
"""

import sys
from pathlib import Path

# --- Пути -------------------------------------------------------------------

# Корень проекта: <root>/analysis/core/runtime.py -> parents[2] == <root>
PROJECT_ROOT = Path(__file__).resolve().parents[2]

DATA_DIR = PROJECT_ROOT / "data"
REPORTS_DIR = PROJECT_ROOT / "reports"
LOGS_DIR = PROJECT_ROOT / "logs"
WEIGHTS_DIR = PROJECT_ROOT / "weights"

DB_FILE = DATA_DIR / "stocks.db"
FINBERT_WEIGHTS = WEIGHTS_DIR / "finbert_lora_final"
QWEN_WEIGHTS = WEIGHTS_DIR / "qwen2_lora_merged"

# Совместимость со старым расположением весов (data/)
_FINBERT_LEGACY = DATA_DIR / "finbert_lora_final"
_QWEN_LEGACY = DATA_DIR / "qwen2_lora_merged"


def get_weights_dir() -> Path:
    """Вернуть директорию с весами LLM (weights/, либо data/ для совместимости)."""
    if FINBERT_WEIGHTS.exists() or QWEN_WEIGHTS.exists():
        return WEIGHTS_DIR
    if _FINBERT_LEGACY.exists() or _QWEN_LEGACY.exists():
        return DATA_DIR
    return WEIGHTS_DIR


def get_finbert_weights() -> Path:
    return get_weights_dir() / "finbert_lora_final"


def get_qwen_weights() -> Path:
    return get_weights_dir() / "qwen2_lora_merged"


def ensure_dirs() -> None:
    """Создать рабочие папки, если их ещё нет (первый запуск)."""
    for d in (DATA_DIR, REPORTS_DIR, LOGS_DIR, WEIGHTS_DIR):
        d.mkdir(parents=True, exist_ok=True)


def setup_logging(name: str = "stock_monitor", level: int = None) -> None:
    """Настроить логирование в консоль + файл logs/<name>.log (idempotent)."""
    import logging

    if getattr(setup_logging, "_done", False):
        return

    from analysis.core.config import LOG_LEVEL, LOG_TO_FILE

    if level is None:
        level = LOG_LEVEL

    ensure_dirs()
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    root = logging.getLogger()
    root.setLevel(level)

    # консоль
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(fmt)
    root.addHandler(ch)

    # файл
    if LOG_TO_FILE:
        fh = logging.FileHandler(LOGS_DIR / f"{name}.log", encoding="utf-8")
        fh.setFormatter(fmt)
        root.addHandler(fh)

    setup_logging._done = True


def db_exists() -> bool:
    """Существует ли файл базы данных?"""
    return DB_FILE.exists()


def get_db_stats() -> dict:
    """Краткая статистика базы данных.

    Returns:
        dict: {'exists': bool, 'stocks': int, 'price_history': int}
    """
    stats = {"exists": DB_FILE.exists(), "stocks": 0, "price_history": 0}
    if not stats["exists"]:
        return stats
    try:
        import sqlite3
        con = sqlite3.connect(str(DB_FILE), timeout=10)
        try:
            for table in ("stocks", "price_history"):
                try:
                    stats[table] = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                except sqlite3.Error:
                    stats[table] = 0
        finally:
            con.close()
    except Exception:
        pass
    return stats


def has_tickers() -> bool:
    """Есть ли в базе список акций (таблица stocks)?"""
    return get_db_stats()["stocks"] > 0


def has_price_history() -> bool:
    """Есть ли в базе история котировок?"""
    return get_db_stats()["price_history"] > 0


def is_first_run() -> bool:
    """Первый ли запуск проекта (нет базы или в ней нет тикеров)?"""
    return not has_tickers()
