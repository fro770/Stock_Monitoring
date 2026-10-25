#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
setup_first_run.py — скрипт САМОГО ПЕРВОГО запуска проекта STOCK_MONITORING
на новом устройстве.

Что делает (по шагам; не просто предупреждает, а предлагает исправления):
  1. Проверяет операционную систему и её версию (Windows / macOS / Linux).
  2. Проверяет мощность ПК: ОЗУ, количество ядер CPU, свободное место на диске.
  3. Ищет Python нужной версии (целевая — 3.11.9); при отсутствии даёт
     прямые ссылки на скачивание и инструкции по установке под каждую ОС.
  4. Создаёт виртуальное окружение .venv (если его нет) и обновляет в нём pip.
  5. Устанавливает библиотеки из requirements.txt в .venv
     (PyTorch — с официального CPU-индекса download.pytorch.org).
  6. Проверяет правильность архитектуры проекта: структура папок/файлов,
     отсутствие устаревших файлов в корне, импортируемость ключевых модулей.
  7. Проверяет доступ к MOEX ISS API.
  8. Формирует итоговый отчёт (OK/WARN/ERROR) с командами запуска проекта.

Запуск (подойдёт любой Python 3.8+):
    Windows    : py setup_first_run.py        (или python setup_first_run.py)
    Linux/macOS: python3 setup_first_run.py

Флаги:
    --skip-install   не устанавливать библиотеки (остальные шаги выполняются)
    --check-only     только диагностика, без создания venv и установки пакетов
    --yes            автоответ «да» на все предложения исправить автоматически
"""

import argparse
import os
import platform
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
VENV_DIR = PROJECT_ROOT / ".venv"
REQUIREMENTS = PROJECT_ROOT / "requirements.txt"

# Желаемая версия интерпретатора внутри venv (см. PROJECT_DESCRIPTION.md)
TARGET_PY = (3, 11)          # major/minor целевой версии
TARGET_PY_STR = "3.11.9"
MIN_PY = (3, 10)             # минимально допустимая для зависимостей проекта

IS_WIN = sys.platform.startswith("win")
IS_MAC = sys.platform == "darwin"

VENV_PY = VENV_DIR / ("Scripts/python.exe" if IS_WIN else "bin/python")

LINKS = {
    "python_win": "https://www.python.org/downloads/windows/",
    "python_mac": "https://www.python.org/downloads/macos/",
    "python_lin": "https://docs.python.org/3/using/unix.html#getting-and-installing-the-latest-version-of-python",
    "python_ftp_3119": "https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe",
    "torch_cpu": "https://pytorch.org/get-started/locally/",
    "git": "https://git-scm.com/downloads",
    "readme": str(PROJECT_ROOT / "PROJECT_DESCRIPTION.md"),
}

OK, WARN, ERR, INFO = "OK", "WARN", "ERROR", "INFO"
_results = []  # список (level, area, message) для итогового отчёта
ASK_ARGS = {"yes": False}


def say(level, area, msg):
    _results.append((level, area, msg))
    icon = {OK: "[OK]   ", WARN: "[ВНИМ]", ERR: "[ОШИБ]", INFO: "[ИНФО] "}
    print(f"  {icon[level]} {area}: {msg}")


def ask(question, default_yes=True):
    """Интерактивный вопрос (с поддержкой авто-режима --yes)."""
    if ASK_ARGS["yes"]:
        return True
    suffix = " [Y/n]: " if default_yes else " [y/N]: "
    try:
        ans = input("  " + question + suffix).strip().lower()
    except EOFError:
        return default_yes
    if not ans:
        return default_yes
    return ans in ("y", "yes", "д", "да")


def run(cmd, timeout=None):
    """Запуск команды без shell, возврат CompletedProcess (текст в UTF-8)."""
    return subprocess.run(cmd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=timeout)


# ------------------------------------------------------------------ helpers
def get_total_ram_gb():
    if IS_WIN:
        for cmd in (
            ["powershell", "-NoProfile", "-Command",
             "(Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory"],
            ["wmic", "ComputerSystem", "get", "TotalPhysicalMemory", "/value"],
        ):
            try:
                out = run(cmd, timeout=30)
                digits = "".join(ch for ch in out.stdout if ch.isdigit())
                if digits:
                    return int(digits) / (1024 ** 3)
            except Exception:
                pass
    try:
        return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / (1024 ** 3) # type: ignore
    except (ValueError, OSError, AttributeError):
        return None


def get_free_disk_gb(path):
    try:
        return shutil.disk_usage(str(path)).free / (1024 ** 3)
    except Exception:
        return None


def find_python_versions():
    """Собирает доступные интерпретаторы: {(major, minor): путь}."""
    found = {}
    candidates = (["py"] if IS_WIN else []) + \
                 ["python3.11", "python3.12", "python3.10", "python3", "python"]
    for c in candidates:
        exe = shutil.which(c)
        if not exe:
            continue
        if c == "py":  # Windows launcher: перечисляем все установленные версии
            out = run([exe, "-0p"])
            for line in out.stdout.splitlines():
                if "-V:" not in line:
                    continue
                try:
                    ver_str = line.split("-V:", 1)[1].split()[0].rstrip("*").strip()
                    full = line.split(ver_str, 1)[-1].strip().lstrip("* ").strip()
                    v = tuple(int(x) for x in ver_str.split(".")[:2])
                    if full and os.path.exists(full):
                        found.setdefault(v, full)
                except (ValueError, IndexError):
                    continue
            continue
        out = run([exe, "-c", "import sys;print('.'.join(map(str,sys.version_info[:2])))"])
        if out.returncode != 0:
            continue
        try:
            v = tuple(int(x) for x in out.stdout.strip().split(".")[:2])
            found.setdefault(v, exe)
        except ValueError:
            continue
    return found


# ============================================================ ШАГ 1: ОС
def step_os():
    print("\n" + "=" * 70)
    print("ШАГ 1/7. Проверка операционной системы")
    print("=" * 70)
    system, release, machine = platform.system(), platform.release(), platform.machine()
    print(f"  {system} {release} ({machine}) | Python запуска: {platform.python_version()}")

    unsupported = False
    if system == "Windows":
        old = any(release.startswith(p) for p in ("5.1", "6.0", "6.1", "6.2", "6.3"))
        if old:
            say(ERR, "ОС", f"Windows NT {release} слишком старая (нужна Windows 10/11 x64).")
            unsupported = True
        else:
            say(OK, "ОС", f"Windows (NT {release}) подходит.")
        if machine.lower() not in ("amd64", "x86_64"):
            say(WARN, "ОС", f"Архитектура {machine}: часть wheels (например, torch) может отсутствовать.")
    elif system == "Darwin":
        say(OK, "ОС", f"macOS {release} подходит (нужна macOS 10.13+).")
    elif system == "Linux":
        distro = ""
        try:
            for line in Path("/etc/os-release").read_text().splitlines():
                if line.startswith("PRETTY_NAME="):
                    distro = line.split("=", 1)[1].strip('"')
        except OSError:
            pass
        say(OK, "ОС", f"Linux {release}" + (f" ({distro})" if distro else "") + " подходит.")
    else:
        say(WARN, "ОС", f"Неизвестная ОС '{system}' — проект на Python должен работать, но инструкции ниже даны для Win/Linux/macOS.")

    if unsupported:
        print(textwrap.dedent("""
          ➤ КАК ИСПРАВИТЬ: обновите ОС. Требуется Windows 10 (версия 1809+) или Windows 11 x64.
            Инструкции по обновлению: https://support.microsoft.com/windows
        """))
    return not unsupported


# ======================================================= ШАГ 2: мощность ПК
def step_hardware():
    print("\n" + "=" * 70)
    print("ШАГ 2/7. Проверка мощности ПК")
    print("=" * 70)
    cpus = os.cpu_count() or 1
    ram = get_total_ram_gb()
    disk = get_free_disk_gb(PROJECT_ROOT)

    print(f"  Ядра CPU: {cpus} | ОЗУ: {ram:.1f} ГБ | Свободно на диске: {disk:.1f} ГБ"
          if ram and disk is not None else
          f"  Ядра CPU: {cpus} | ОЗУ: {'%.1f ГБ' % ram if ram else 'н/д'} | "
          f"Диск: {'%.1f ГБ' % disk if disk is not None else 'н/д'}")

    ok = True
    if cpus < 4:
        say(WARN, "CPU", f"Всего {cpus} ядер — анализ будет медленным (загрузка данных рассчитана на 6+ потоков).")
    else:
        say(OK, "CPU", f"{cpus} ядер — достаточно.")

    if ram is None:
        say(INFO, "RAM", "Не удалось определить объём ОЗУ автоматически.")
    elif ram < 8:
        say(ERR, "RAM", f"ОЗУ {ram:.1f} ГБ < 8 ГБ — обучение ML-моделей и LLM-компоненты не поместятся в память.")
        print(textwrap.dedent("""
          ➤ КАК ИСПРАВИТЬ: увеличьте ОЗУ минимум до 8 ГБ (рекомендуется 16 ГБ).
            Временно используйте «Режим 1» (быстрый, без ML) и ограничьте выборку: --top-n 20.
        """))
        ok = False
    elif ram < 16:
        say(WARN, "RAM", f"ОЗУ {ram:.1f} ГБ — базового анализа хватит, глубокий режим (LLM) может не помещаться. Рекомендуется 16 ГБ.")
    else:
        say(OK, "RAM", f"{ram:.1f} ГБ — отлично.")

    if disk is not None:
        if disk < 5:
            say(ERR, "DISK", f"Свободно {disk:.1f} ГБ < 5 ГБ — не хватит на окружение (~3–4 ГБ) и базу котировок.")
            print("  ➤ КАК ИСПРАВИТЬ: освободите место или перенесите проект на диск с запасом ≥ 10 ГБ.")
            ok = False
        elif disk < 10:
            say(WARN, "DISK", f"Свободно {disk:.1f} ГБ — хватит, но впритык (зависимости ~3–4 ГБ + рост БД). Рекомендовано ≥ 10 ГБ.")
        else:
            say(OK, "DISK", f"Свободно {disk:.1f} ГБ — достаточно.")
    return ok


# ======================================================== ШАГ 3: версия Python
def _python_install_help():
    dl = LINKS["python_win"] if IS_WIN else (LINKS["python_mac"] if IS_MAC else LINKS["python_lin"])
    return textwrap.dedent(f"""
      ➤ КАК ИСПРАВИТЬ — установите Python {TARGET_PY_STR}:
        • Windows: страница загрузок {dl}
          прямая ссылка на инсталлятор: {LINKS['python_ftp_3119']}
          При установке ОБЯЗАТЕЛЬНО отметьте «Add python.exe to PATH».
        • macOS:   {dl}  (или: brew install python@3.11)
        • Linux:   {dl}
          Ubuntu/Debian: sudo apt install python3.11 python3.11-venv
          Fedora:        sudo dnf install python3.11
        После установки перезапустите этот скрипт:
          Windows: py -3.11 setup_first_run.py | Linux/macOS: python3.11 setup_first_run.py
    """)


def step_python():
    print("\n" + "=" * 70)
    print(f"ШАГ 3/7. Проверка версии Python (целевая: {TARGET_PY_STR})")
    print("=" * 70)
    versions = find_python_versions()
    if versions:
        pretty = ", ".join(f"{'.'.join(map(str, k))} → {v}" for k, v in sorted(versions.items()))
        say(INFO, "PYTHON", f"Найдено в системе: {pretty}")
    else:
        say(ERR, "PYTHON", "Ни один интерпретатор Python не найден в PATH!")
        print(_python_install_help())
        return None

    if TARGET_PY in versions:
        say(OK, "PYTHON", f"Python {'.'.join(map(str, TARGET_PY))} найден: {versions[TARGET_PY]}")
        return versions[TARGET_PY]

    suitable = [v for v in versions if v[0] == 3 and v >= MIN_PY]
    if suitable:
        best = min(suitable, key=lambda v: (abs(v[0] - TARGET_PY[0]), abs(v[1] - TARGET_PY[1])))
        say(WARN, "PYTHON", f"Python {TARGET_PY_STR} не найден; ближайший подходящий — {'.'.join(map(str, best))}. "
                            "requirements.txt собран под 3.11 (для 3.12+ пакеты подобраны совместимые, но проверьте результат).")
        if ask(f"Использовать Python {'.'.join(map(str, best))} для создания окружения?", default_yes=True):
            return versions[best]
        print(_python_install_help())
        return None

    say(ERR, "PYTHON", "Нет Python версии ≥ 3.10.")
    print(_python_install_help())
    return None


# ================================================ ШАГ 4: виртуальное окружение
def step_venv(python_exe, check_only):
    print("\n" + "=" * 70)
    print("ШАГ 4/7. Виртуальное окружение (.venv)")
    print("=" * 70)
    if VENV_PY.exists():
        out = run([str(VENV_PY), "-c", "import sys;print('.'.join(map(str,sys.version_info[:3])))"])
        ver = out.stdout.strip() if out.returncode == 0 else "?"
        say(OK, "VENV", f"Окружение уже существует: {VENV_DIR} (Python {ver})")
        try:
            if ver != "?" and tuple(int(x) for x in ver.split(".")[:2]) < MIN_PY:
                say(WARN, "VENV", f"Python внутри .venv ({ver}) слишком старый. "
                                  f"➤ Исправление: удалите папку .venv и перезапустите скрипт.")
                return False
        except ValueError:
            pass
        return True

    if check_only:
        say(WARN, "VENV", "Окружение .venv отсутствует (режим --check-only: создавать не буду).")
        return False

    if python_exe is None:
        say(ERR, "VENV", "Нечем создавать окружение — нет подходящего Python (см. шаг 3).")
        return False

    say(INFO, "VENV", f"Создаю виртуальное окружение: {VENV_DIR} (интерпретатор: {python_exe}) ...")
    out = run([python_exe, "-m", "venv", str(VENV_DIR)], timeout=300)
    if out.returncode != 0 or not VENV_PY.exists():
        err = (out.stderr or out.stdout or "").strip()
        say(ERR, "VENV", f"Не удалось создать окружение: {err[:300]}")
        print(textwrap.dedent("""
          ➤ КАК ИСПРАВИТЬ:
            • Linux: не установлен модуль venv:
                sudo apt install python3.11-venv   (Ubuntu/Debian)
                sudo dnf install python3.11-devel  (Fedora)
            • Windows: переустановите Python с python.org, компонент «pip» должен быть включён.
        """))
        return False
    say(OK, "VENV", "Окружение создано успешно.")
    say(INFO, "VENV", "Обновляю pip в окружении ...")
    run([str(VENV_PY), "-m", "pip", "install", "--upgrade", "pip"], timeout=300)
    return True


# ==================================================== ШАГ 5: установка библиотек
def _installed_packages():
    if not VENV_PY.exists():
        return {}
    out = run([str(VENV_PY), "-m", "pip", "list", "--format=json"], timeout=120)
    try:
        import json
        return {p["name"].lower(): p["version"] for p in json.loads(out.stdout)}
    except Exception:
        return {}


def step_install(check_only):
    print("\n" + "=" * 70)
    print("ШАГ 5/7. Установка библиотек из requirements.txt")
    print("=" * 70)
    if not REQUIREMENTS.exists():
        say(ERR, "PIP", "Файл requirements.txt не найден в корне проекта!")
        print("  ➤ КАК ИСПРАВИТЬ: восстановите файл из репозитория: git checkout -- requirements.txt")
        return False

    pkgs = _installed_packages()
    core_checks = ["numpy", "pandas", "scikit-learn", "requests", "openpyxl",
                   "xgboost", "lightgbm", "torch", "customtkinter"]
    missing_core = [c for c in core_checks if c not in pkgs]

    if pkgs and not missing_core:
        say(OK, "PIP", f"Все ключевые библиотеки уже установлены ({len(pkgs)} пакетов). Пропускаю установку.")
        return True

    if check_only:
        say(WARN, "PIP", f"Требуется установка: не хватает {', '.join(missing_core)}. "
                         "Режим --check-only: не устанавливаю. Запустите скрипт без этого флага.")
        return False

    say(INFO, "PIP", (f"Не хватает: {', '.join(missing_core)}. Доустанавливаю ..." if pkgs
                      else "Пакеты не установлены. Установка займёт 5–20 минут и ~3–4 ГБ на диске ..."))
    if not ask("Запустить установку сейчас?", default_yes=True):
        say(WARN, "PIP", "Установка пропущена по вашему решению — проект не готов к работе.")
        return False

    # PyTorch ставим отдельно с CPU-индекса (обычный PyPI тянет CUDA-сборку ~2.5 ГБ)
    if "torch" not in pkgs:
        say(INFO, "PIP", "Шаг A: PyTorch (CPU) с официального индекса download.pytorch.org ...")
        out = run([str(VENV_PY), "-m", "pip", "install",
                   "torch==2.4.1", "torchvision==0.19.1", "torchaudio==2.4.1",
                   "--index-url", "https://download.pytorch.org/whl/cpu"], timeout=1800)
        if out.returncode != 0:
            say(WARN, "PIP", "CPU-индекс недоступен — torch попробую установить из общего PyPI вместе с остальными пакетами.")

    say(INFO, "PIP", "Шаг B: установка зависимостей из requirements.txt ...")
    out = run([str(VENV_PY), "-m", "pip", "install", "-r", str(REQUIREMENTS)], timeout=3600)
    if out.returncode != 0:
        tail = (out.stderr or out.stdout or "")[-1200:]
        say(ERR, "PIP", "pip завершился с ошибкой. Последние строки лога:")
        print("  " + "\n  ".join(tail.splitlines()))
        print(textwrap.dedent(f"""
          ➤ КАК ИСПРАВИТЬ типовые причины:
            • SSL/прокси:  проверьте интернет; в корпоративной сети задайте HTTPS_PROXY или:
                {VENV_PY} -m pip install --trusted-host pypi.org --trusted-host files.pythonhosted.org -r requirements.txt
            • Мало места:  освободите ≥ 5 ГБ (см. шаг 2);
            • Сборка из исходников: убедитесь, что pip обновлён и Python в .venv ≥ 3.10;
            • Проблема с torch: ручная установка по инструкции {LINKS['torch_cpu']}
        """))
        return False

    pkgs = _installed_packages()
    still_missing = [c for c in core_checks if c not in pkgs]
    if still_missing:
        say(WARN, "PIP", f"Установка завершена, но не найдены: {', '.join(still_missing)}")
    else:
        say(OK, "PIP", f"Все библиотеки установлены ({len(pkgs)} пакетов).")
    return not still_missing


# ================================================ ШАГ 6: проверка архитектуры
EXPECTED_DIRS = ["analysis", "analysis/core", "analysis/models", "analysis/scripts",
                 "analysis/ui", "analysis/utils", "data", "models", "reports", "logs"]
EXPECTED_FILES = ["main.py", "requirements.txt", "PROJECT_DESCRIPTION.md",
                  "analysis/main.py", "analysis/reporter.py",
                  "analysis/core/runtime.py", "analysis/core/db_manager.py",
                  "analysis/core/history_updater.py", "analysis/core/moex_client.py",
                  "analysis/ui/app.py"]
# файлы, которые НЕ должны лежать в корне (правильное расположение указано справа)
LEGACY_IN_ROOT = {
    "make_excel.py": "analysis/scripts/",
    "test_connection.py": "analysis/scripts/",
    "init_db_and_load.py": "analysis/scripts/ (legacy)",
    "update_data.py": "удалён → analysis/core/history_updater.py",
    "moex_all_shares.xlsx": "data/",
    "moex_all_shares.csv": "data/",
}


def step_architecture(auto_fix):
    print("\n" + "=" * 70)
    print("ШАГ 6/7. Проверка правильности архитектуры проекта")
    print("=" * 70)
    problems = 0

    for d in EXPECTED_DIRS:
        p = PROJECT_ROOT / d
        if p.is_dir():
            continue
        if auto_fix and not d.startswith("analysis"):
            p.mkdir(parents=True, exist_ok=True)
            say(WARN, "ARCH", f"Папка {d}/ отсутствовала — создал пустую.")
        else:
            problems += 1
            say(ERR, "ARCH", f"Отсутствует обязательная папка: {d}/")
            print(f"  ➤ КАК ИСПРАВИТЬ: git checkout -- {d}   (или клонируйте репозиторий заново, Git: {LINKS['git']})")

    for f in EXPECTED_FILES:
        if (PROJECT_ROOT / f).is_file():
            continue
        problems += 1
        say(ERR, "ARCH", f"Отсутствует обязательный файл: {f}")
        print(f"  ➤ КАК ИСПРАВИТЬ: git checkout -- {f}")

    orphan_found = False
    for name, dest in LEGACY_IN_ROOT.items():
        src = PROJECT_ROOT / name
        if not src.exists():
            continue
        orphan_found = True
        if auto_fix and name in ("make_excel.py", "test_connection.py") and \
                (PROJECT_ROOT / "analysis/scripts" / name).exists():
            src.unlink()
            say(WARN, "ARCH", f"Устаревший дубликат {name} в корне — удалён (основной: analysis/scripts/{name}).")
        elif auto_fix and name in ("moex_all_shares.xlsx", "moex_all_shares.csv") and \
                not (PROJECT_ROOT / "data" / name).exists():
            shutil.move(str(src), str(PROJECT_ROOT / "data" / name))
            say(WARN, "ARCH", f"Файл {name} перенесён из корня в data/.")
        else:
            problems += 1
            say(WARN, "ARCH", f"Устаревший файл в корне: {name} → правильное место: {dest}")
            print(f"  ➤ РЕКОМЕНДАЦИЯ: перенесите или удалите {name} (архитектура описана в PROJECT_DESCRIPTION.md).")

    if not orphan_found:
        say(OK, "ARCH", "В корне проекта нет устаревших/осиротевших файлов.")

    # импортируемость ключевых модулей — тем Python, который будет реально использоваться
    interpreter = str(VENV_PY) if VENV_PY.exists() else sys.executable
    mods = ["analysis.core.runtime", "analysis.core.db_manager",
            "analysis.core.history_updater", "analysis.core.moex_client",
            "analysis.reporter"]
    for m in mods:
        try:
            out = run([interpreter, "-c", f"import {m}"], timeout=120)
        except subprocess.TimeoutExpired:
            problems += 1
            say(ERR, "ARCH", f"Импорт {m}: таймаут (возможно, нехватка ресурсов).")
            continue
        if out.returncode != 0:
            problems += 1
            err_last = (out.stderr or "").strip().splitlines()[-1] if (out.stderr or "").strip() else "?"
            say(ERR, "ARCH", f"Модуль {m} не импортируется: {err_last[:200]}")
            if "No module named" in err_last:
                miss = err_last.split("No module named")[-1].strip().split("'")[1] \
                       if "'" in err_last else "?"
                print(f"  ➤ КАК ИСПРАВИТЬ: пакет '{miss}' не установлен — выполните шаг 5 "
                      f"(перезапустите скрипт БЕЗ --check-only/--skip-install).")
        else:
            say(OK, "ARCH", f"Модуль {m} импортируется корректно.")

    if problems == 0:
        say(OK, "ARCH", "Архитектура проекта корректна.")
    return problems == 0


# ===================================================== ШАГ 7: соединение с MOEX
def step_moex():
    print("\n" + "=" * 70)
    print("ШАГ 7/7. Проверка соединения с MOEX ISS API")
    print("=" * 70)
    try:
        import urllib.request
        import json as _json
        req = urllib.request.Request(
            "https://iss.moex.com/iss/engines/stock/markets/shares/securities.json"
            "?iss.meta=off&iss.limit=1",
            headers={"User-Agent": "StockMonitoring-setup/1.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            _json.loads(r.read().decode("utf-8"))
        say(OK, "MOEX", "API iss.moex.com доступен.")
        return True
    except Exception as e:
        say(ERR, "MOEX", f"Нет доступа к iss.moex.com: {type(e).__name__}: {e}")
        print(textwrap.dedent("""
          ➤ КАК ИСПРАВИТЬ:
            • Проверьте интернет и откройте https://iss.moex.com в браузере;
            • Корпоративный файрвол/прокси: задайте переменные HTTPS_PROXY/HTTP_PROXY
              или обратитесь к сетевому администратору;
            • Без доступа к MOEX проект сможет работать только с ранее загруженной базой.
        """))
        return False


# ============================================================ Итоговый отчёт
def activate_hint():
    return r".venv\Scripts\activate" if IS_WIN else "source .venv/bin/activate"


def summary(setup_ok, arch_ok):
    print("\n" + "=" * 70)
    print("ИТОГОВЫЙ ОТЧЁТ")
    print("=" * 70)
    errs = [r for r in _results if r[0] == ERR]
    warns = [r for r in _results if r[0] == WARN]
    oks = [r for r in _results if r[0] == OK]
    print(f"  Успешно: {len(oks)} | Предупреждений: {len(warns)} | Ошибок: {len(errs)}")

    if warns:
        print("\n  Предупреждения:")
        for _, area, msg in warns:
            print(f"    ⚠ [{area}] {msg}")
    if errs:
        print("\n  Ошибки (инструкции «КАК ИСПРАВИТЬ» — выше по ходу вывода):")
        for _, area, msg in errs:
            print(f"    ❌ [{area}] {msg}")

    print("\n" + "-" * 70)
    if setup_ok and arch_ok:
        print("  🎉 Система готова к работе! Как запустить проект:")
        print(f"     1) Активируйте окружение:  {activate_hint()}")
        print(f"     2) Запустите интерфейс:    python main.py")
        print("        На вкладке «Главная» нажмите «🚀 Первый запуск» —")
        print("        программа сама создаст БД, скачает список акций и историю котировок с MOEX.")
        print("        Вариант без GUI:  python main.py --no-gui")
    else:
        print("  ⛔ Система НЕ готова. Исправьте ошибки выше и перезапустите:")
        print("     Windows: py setup_first_run.py | Linux/macOS: python3 setup_first_run.py")
    print("-" * 70)
    print(f"  Полная документация: {LINKS['readme']}")
    print("=" * 70)


# ==================================================================== main
def main():
    parser = argparse.ArgumentParser(
        description="Первоначальная настройка STOCK_MONITORING на новом устройстве")
    parser.add_argument("--skip-install", action="store_true",
                        help="не устанавливать библиотеки (остальные проверки выполняются)")
    parser.add_argument("--check-only", action="store_true",
                        help="только диагностика: ничего не создавать и не устанавливать")
    parser.add_argument("--yes", action="store_true",
                        help="автоответ «да» на все предложения об автоматическом исправлении")
    args = parser.parse_args()
    ASK_ARGS["yes"] = args.yes or not sys.stdin.isatty()

    print("=" * 70)
    print("  STOCK MONITORING — первичная настройка нового устройства")
    print("=" * 70)
    print(f"  Проект: {PROJECT_ROOT}")
    if args.check_only:
        print("  Режим: --check-only (диагностика без изменений)")

    os_ok = step_os()
    step_hardware()
    python_exe = step_python()
    venv_ok = step_venv(python_exe, args.check_only)

    if args.check_only:
        install_ok = step_install(True)
    elif args.skip_install:
        install_ok = bool(_installed_packages())
        if not install_ok:
            say(INFO, "PIP", "Установка пропущена (--skip-install) — библиотеки могут отсутствовать.")
    else:
        install_ok = step_install(False) if venv_ok else False

    auto_fix = (not args.check_only) and ASK_ARGS["yes"]
    if not args.check_only and not ASK_ARGS["yes"]:
        auto_fix = ask("Исправлять проблемы архитектуры автоматически (перенос/удаление дублей)?",
                       default_yes=True)
    arch_ok = step_architecture(auto_fix)
    step_moex()

    if not os_ok:
        say(ERR, "ИТОГ", "ОС не поддерживается — дальнейшая работа невозможна без обновления системы.")

    summary(install_ok and venv_ok, arch_ok)
    return 0 if (os_ok and venv_ok and install_ok and arch_ok) else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nПрервано пользователем.")
        sys.exit(130)
