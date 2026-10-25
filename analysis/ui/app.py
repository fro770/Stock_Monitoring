"""
Графический интерфейс Stock Monitoring (CustomTkinter)

Вкладки:
  🏠 Главная      — статус системы, кнопки первого запуска / обновления / анализа
  ⚙️ Анализ       — параметры анализа + запуск + таблица результатов
  🗄 База данных  — статистика БД, инициализация, обновление котировок
  📁 Отчёты      — список сгенерированных отчётов, открытие папки/файлов
  🧪 Проверка    — диагностика соединения, БД, модулей; лог запуска
  ℹ О программе  — сведения о проекте

Все длительные операции выполняются в фоновых потоках; обновления UI —
через очередь сообщений (поток-safe).
"""

import logging
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from datetime import datetime
from tkinter import filedialog, messagebox

import customtkinter as ctk

from analysis.core.config import Config
from analysis.core.runtime import (
    PROJECT_ROOT, REPORTS_DIR, LOGS_DIR, DB_FILE,
    ensure_dirs, get_db_stats, is_first_run,
)

logger = logging.getLogger(__name__)

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

GREEN = "#2fa572"
RED = "#e05c5c"
ORANGE = "#e0a458"


def open_path(path: str) -> None:
    """Открыть файл/папку в системном проводнике (Windows/macOS/Linux)."""
    if not path or not os.path.exists(path):
        return
    try:
        if sys.platform.startswith("win"):
            os.startfile(path)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception as e:
        logger.warning("Не удалось открыть %s: %s", path, e)


class App(ctk.CTk):
    """Главное окно приложения."""

    def __init__(self):
        super().__init__()
        self.title("📊 Stock Monitoring — анализ и прогноз акций MOEX")
        self.geometry("1060x700")
        self.minsize(900, 600)

        ensure_dirs()

        self._queue: "queue.Queue[tuple]" = queue.Queue()
        self._worker: threading.Thread | None = None
        self._cancel_event = threading.Event()
        self._busy = False

        self._build_layout()
        self._refresh_status()
        self.after(100, self._process_queue)

        # Подсказка при первом запуске
        if is_first_run():
            self._log("ℹ Обнаружен ПЕРВЫЙ ЗАПУСК: база данных пуста.")
            self._log("   Нажмите «🚀 Первый запуск» на вкладке «Главная» — "
                      "система сама создаст БД и загрузит список акций с MOEX.")

    # ------------------------------------------------------------------ layout

    def _build_layout(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # Шапка
        self.header = ctk.CTkFrame(self, corner_radius=0)
        self.header.grid(row=0, column=0, sticky="ew")
        self.header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            self.header, text="📊 Stock Monitoring",
            font=ctk.CTkFont(size=20, weight="bold"),
        ).grid(row=0, column=0, padx=20, pady=10, sticky="w")

        self.status_label = ctk.CTkLabel(self.header, text="", font=ctk.CTkFont(size=13))
        self.status_label.grid(row=0, column=1, padx=20, pady=10, sticky="e")

        self.progress = ctk.CTkProgressBar(self.header, width=220, mode="determinate")
        self.progress.grid(row=0, column=2, padx=(0, 20), pady=10)
        self.progress.set(0)

        # Вкладки
        self.tabs = ctk.CTkTabview(self)
        self.tabs.grid(row=1, column=0, sticky="nsew", padx=12, pady=(4, 12))
        self.tab_home = self.tabs.add("🏠 Главная")
        self.tab_analysis = self.tabs.add("⚙️ Анализ")
        self.tab_db = self.tabs.add("🗄 База данных")
        self.tab_reports = self.tabs.add("📁 Отчёты")
        self.tab_checks = self.tabs.add("🧪 Проверка")
        self.tab_about = self.tabs.add("ℹ О программе")

        self._build_home_tab()
        self._build_analysis_tab()
        self._build_db_tab()
        self._build_reports_tab()
        self._build_checks_tab()
        self._build_about_tab()

    # --- Главная -------------------------------------------------------------

    def _build_home_tab(self):
        t = self.tab_home
        t.grid_columnconfigure(0, weight=1)

        box = ctk.CTkFrame(t)
        box.grid(row=0, column=0, sticky="new", padx=10, pady=10)
        box.grid_columnconfigure((0, 1, 2), weight=1)

        ctk.CTkLabel(box, text="Основные действия",
                     font=ctk.CTkFont(size=16, weight="bold")).grid(
            row=0, column=0, columnspan=3, pady=(12, 6), sticky="w", padx=14)

        self.btn_first_run = ctk.CTkButton(
            box, text="🚀 Первый запуск\n(создать БД + загрузить акции)",
            height=64, command=self.on_first_run)
        self.btn_first_run.grid(row=1, column=0, padx=10, pady=10, sticky="nsew")

        self.btn_update = ctk.CTkButton(
            box, text="🔄 Обновить данные\n(история котировок)",
            height=64, command=self.on_update_history)
        self.btn_update.grid(row=1, column=1, padx=10, pady=10, sticky="nsew")

        self.btn_analyze = ctk.CTkButton(
            box, text="📈 Запустить анализ\n(с текущих настроек)",
            height=64, fg_color=GREEN, hover_color="#268a5f",
            command=lambda: self.on_run_analysis())
        self.btn_analyze.grid(row=1, column=2, padx=10, pady=10, sticky="nsew")

        # Статус системы
        stat = ctk.CTkFrame(t)
        stat.grid(row=1, column=0, sticky="new", padx=10, pady=6)
        stat.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(stat, text="Состояние системы",
                     font=ctk.CTkFont(size=16, weight="bold")).grid(
            row=0, column=0, pady=(12, 6), sticky="w", padx=14)
        self.home_status = ctk.CTkLabel(stat, text="", justify="left",
                                        font=ctk.CTkFont(size=13))
        self.home_status.grid(row=1, column=0, padx=14, pady=(0, 12), sticky="w")

        # Журнал
        logbox = ctk.CTkFrame(t)
        logbox.grid(row=2, column=0, sticky="nsew", padx=10, pady=6)
        t.grid_rowconfigure(2, weight=1)
        logbox.grid_rowconfigure(1, weight=1)
        logbox.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(logbox, text="Журнал событий",
                     font=ctk.CTkFont(size=14, weight="bold")).grid(
            row=0, column=0, pady=(8, 2), sticky="w", padx=12)
        self.log_area = ctk.CTkTextbox(logbox, height=180, font=ctk.CTkFont(family="Consolas", size=12))
        self.log_area.grid(row=1, column=0, sticky="nsew", padx=10, pady=(2, 10))

        btns = ctk.CTkFrame(t, fg_color="transparent")
        btns.grid(row=3, column=0, sticky="ew", padx=10, pady=(0, 10))
        ctk.CTkButton(btns, text="📂 Открыть папку отчётов", width=200,
                      command=lambda: open_path(str(REPORTS_DIR))).pack(side="left", padx=(0, 8))
        ctk.CTkButton(btns, text="🗑 Очистить журнал", width=130,
                      command=self.log_area.delete).pack(side="left")

    # --- Анализ ----------------------------------------------------------------

    def _build_analysis_tab(self):
        t = self.tab_analysis
        t.grid_columnconfigure(0, weight=1)
        t.grid_rowconfigure(3, weight=1)

        form = ctk.CTkFrame(t)
        form.grid(row=0, column=0, sticky="new", padx=10, pady=10)
        for c in range(4):
            form.grid_columnconfigure(c, weight=1)

        ctk.CTkLabel(form, text="Параметры анализа",
                     font=ctk.CTkFont(size=16, weight="bold")).grid(
            row=0, column=0, columnspan=4, sticky="w", padx=14, pady=(12, 6))

        # Топ N
        ctk.CTkLabel(form, text="Количество топ-акций:").grid(row=1, column=0, sticky="w", padx=14, pady=6)
        self.var_topn = ctk.CTkOptionMenu(form, values=["10", "20", "50", "100", "259"])
        self.var_topn.set("20")
        self.var_topn.grid(row=1, column=1, sticky="w", pady=6)

        # Тип акций
        ctk.CTkLabel(form, text="Тип акций:").grid(row=1, column=2, sticky="w", padx=14, pady=6)
        self.var_stocktype = ctk.CTkOptionMenu(
            form, values=["Все", "Обыкновенные", "Привилегированные"])
        self.var_stocktype.set("Все")
        self.var_stocktype.grid(row=1, column=3, sticky="w", pady=6)

        # Режим
        ctk.CTkLabel(form, text="Режим анализа:").grid(row=2, column=0, sticky="w", padx=14, pady=6)
        self.var_mode = ctk.CTkOptionMenu(
            form, values=["1 — Быстрый (тренды)", "2 — Стандартный (ML)", "3 — Глубокий (ансамбль)"])
        self.var_mode.set("2 — Стандартный (ML)")
        self.var_mode.grid(row=2, column=1, sticky="w", pady=6)

        # Уверенность
        ctk.CTkLabel(form, text="Мин. уверенность:").grid(row=2, column=2, sticky="w", padx=14, pady=6)
        frame_conf = ctk.CTkFrame(form, fg_color="transparent")
        frame_conf.grid(row=2, column=3, sticky="w", pady=6)
        self.slider_conf = ctk.CTkSlider(frame_conf, from_=0, to=100, width=140)
        self.slider_conf.set(50)
        self.slider_conf.pack(side="left")
        self.lbl_conf = ctk.CTkLabel(frame_conf, text="50%")
        self.lbl_conf.pack(side="left", padx=6)
        self.slider_conf.configure(command=lambda v: self.lbl_conf.configure(
            text=f"{int(v)}%"))

        # Дни прогноза
        ctk.CTkLabel(form, text="Дни прогноза (через запятую):").grid(
            row=3, column=0, sticky="w", padx=14, pady=6)
        self.ent_days = ctk.CTkEntry(form, width=160)
        self.ent_days.insert(0, "1,7,14,30")
        self.ent_days.grid(row=3, column=1, sticky="w", pady=6)

        runbar = ctk.CTkFrame(t, fg_color="transparent")
        runbar.grid(row=4, column=0, sticky="ew", padx=10, pady=(0, 6))
        self.btn_run = ctk.CTkButton(runbar, text="▶ Начать анализ", width=180,
                                     fg_color=GREEN, hover_color="#268a5f",
                                     command=self.on_run_analysis)
        self.btn_run.pack(side="left", padx=(0, 8))
        self.btn_stop = ctk.CTkButton(runbar, text="⏹ Остановить", width=120,
                                      fg_color=RED, hover_color="#b84a4a",
                                      state="disabled", command=self.on_cancel)
        self.btn_stop.pack(side="left")

        # Результаты
        res = ctk.CTkFrame(t)
        res.grid(row=5, column=0, sticky="nsew", padx=10, pady=(0, 10))
        t.grid_rowconfigure(5, weight=1)
        res.grid_rowconfigure(1, weight=1)
        res.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(res, text="Результаты (топ акций по прогнозу роста)",
                     font=ctk.CTkFont(size=14, weight="bold")).grid(
            row=0, column=0, sticky="w", padx=12, pady=(8, 2))
        self.results_area = ctk.CTkTextbox(
            res, font=ctk.CTkFont(family="Consolas", size=12), wrap="none")
        self.results_area.grid(row=1, column=0, sticky="nsew", padx=10, pady=(2, 10))

    # --- База данных ------------------------------------------------------------

    def _build_db_tab(self):
        t = self.tab_db
        t.grid_columnconfigure(0, weight=1)

        card = ctk.CTkFrame(t)
        card.grid(row=0, column=0, sticky="new", padx=10, pady=10)
        card.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(card, text="База данных",
                     font=ctk.CTkFont(size=16, weight="bold")).grid(
            row=0, column=0, sticky="w", padx=14, pady=(12, 4))
        self.db_info = ctk.CTkLabel(card, text="", justify="left",
                                    font=ctk.CTkFont(size=13))
        self.db_info.grid(row=1, column=0, sticky="w", padx=14, pady=(0, 12))

        btns = ctk.CTkFrame(t, fg_color="transparent")
        btns.grid(row=1, column=0, sticky="ew", padx=10)
        ctk.CTkButton(btns, text="🔨 Создать/обновить схему БД", width=220,
                      command=self.on_init_db).pack(side="left", padx=(0, 8), pady=6)
        ctk.CTkButton(btns, text="📥 Загрузить список акций с MOEX", width=240,
                      command=self.on_load_tickers).pack(side="left", padx=(0, 8), pady=6)
        ctk.CTkButton(btns, text="🔄 Обновить историю котировок", width=220,
                      command=self.on_update_history).pack(side="left", padx=(0, 8), pady=6)
        ctk.CTkButton(btns, text="🧪 Проверить соединение", width=180,
                      command=self.on_check_connection).pack(side="left", padx=(0, 8), pady=6)

        upd = ctk.CTkFrame(t)
        upd.grid(row=2, column=0, sticky="new", padx=10, pady=10)
        upd.grid_columnconfigure((0, 1), weight=1)
        ctk.CTkLabel(upd, text="Параметры обновления истории:",
                     font=ctk.CTkFont(size=14, weight="bold")).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=14, pady=(10, 4))
        ctk.CTkLabel(upd, text="Глубина истории (дней):").grid(
            row=1, column=0, sticky="w", padx=14, pady=6)
        self.var_histdays = ctk.CTkOptionMenu(
            upd, values=["90", "180", "365", "720", "1095"])
        self.var_histdays.set(str(Config.DEFAULT_HISTORY_DAYS))
        self.var_histdays.grid(row=1, column=1, sticky="w", pady=6)

        ctk.CTkLabel(upd, text="Ограничение количества тикеров (0 = все):",
                    ).grid(row=2, column=0, sticky="w", padx=14, pady=6)
        self.ent_limit = ctk.CTkEntry(upd, width=90)
        self.ent_limit.insert(0, "0")
        self.ent_limit.grid(row=2, column=1, sticky="w", pady=6)

        ctk.CTkLabel(t, text="⚠ Полное обновление ~260 тикеров может занять 10–30 минут.",
                     text_color=ORANGE).grid(row=3, column=0, sticky="w", padx=14)

    # --- Отчёты -----------------------------------------------------------------

    def _build_reports_tab(self):
        t = self.tab_reports
        t.grid_columnconfigure(0, weight=1)
        t.grid_rowconfigure(1, weight=1)

        bar = ctk.CTkFrame(t, fg_color="transparent")
        bar.grid(row=0, column=0, sticky="ew", padx=10, pady=10)
        ctk.CTkButton(bar, text="🔄 Обновить список", width=160,
                      command=self._refresh_reports).pack(side="left", padx=(0, 8))
        ctk.CTkButton(bar, text="📂 Открыть папку отчётов", width=200,
                      command=lambda: open_path(str(REPORTS_DIR))).pack(side="left", padx=(0, 8))
        ctk.CTkButton(bar, text="💾 Сохранить копию выбранного...", width=220,
                      command=self.on_save_report_copy).pack(side="left")

        self.reports_list = ctk.CTkScrollableFrame(t, label_text="Файлы в reports/")
        self.reports_list.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))
        self.reports_list.grid_columnconfigure(0, weight=1)
        self._report_rows: list = []
        self._refresh_reports()

    # --- Проверка ----------------------------------------------------------------

    def _build_checks_tab(self):
        t = self.tab_checks
        t.grid_columnconfigure(0, weight=1)
        t.grid_rowconfigure(1, weight=1)

        bar = ctk.CTkFrame(t, fg_color="transparent")
        bar.grid(row=0, column=0, sticky="ew", padx=10, pady=10)
        ctk.CTkButton(bar, text="🧪 Полная диагностика", width=200,
                      command=self.on_full_check).pack(side="left", padx=(0, 8))
        self.btn_backtest = ctk.CTkButton(
            bar, text="🔁 Самопроверка (бэктест)", width=200,
            fg_color="#2b6cb0", hover_color="#234e80",
            command=self.on_run_backtest)
        self.btn_backtest.pack(side="left", padx=(0, 8))
        ctk.CTkButton(bar, text="📝 Открыть папку логов", width=200,
                      command=lambda: open_path(str(LOGS_DIR))).pack(side="left")

        self.checks_area = ctk.CTkTextbox(
            t, font=ctk.CTkFont(family="Consolas", size=12))
        self.checks_area.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))

    # --- О программе ----------------------------------------------------------------

    def _build_about_tab(self):
        t = self.tab_about
        t.grid_columnconfigure(0, weight=1)
        text = (
            "📊 Stock Monitoring — система анализа и прогноза акций MOEX\n\n"
            "Возможности:\n"
            "  • Загрузка списка акций и истории котировок через MOEX ISS API\n"
            "  • SQLite-база данных (data/stocks.db)\n"
            "  • Три режима анализа: быстрый (тренды), стандартный (ML),\n"
            "    глубокий (ансамбль моделей XGBoost/LightGBM/CatBoost + LLM)\n"
            "  • Отчёты в форматах XLSX, CSV и JSON в папке reports/\n\n"
            "Архитектура:\n"
            "  analysis/core     — ядро: MOEX-клиент, БД, конфигурация\n"
            "  analysis/models   — ML-модели и ансамбли\n"
            "  analysis/ui       — этот графический интерфейс\n"
            "  analysis/scripts  — служебные скрипты\n\n"
            f"Корень проекта: {PROJECT_ROOT}\n"
            f"Python: {sys.version.split()[0]}  |  Python 3.11.9 рекомендуется\n\n"
            "⚠ Все прогнозы являются вероятностными оценками и не являются\n"
            "индивидуальной инвестиционной рекомендацией."
        )
        lbl = ctk.CTkLabel(t, text=text, justify="left",
                           font=ctk.CTkFont(size=13))
        lbl.grid(row=0, column=0, sticky="nw", padx=16, pady=16)

    # ------------------------------------------------------------------ helpers

    def _log(self, msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_area.insert("end", f"[{ts}] {msg}\n")
        self.log_area.see("end")

    def _check_msg(self, msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        self.checks_area.insert("end", f"[{ts}] {msg}\n")
        self.checks_area.see("end")

    def _set_busy(self, busy: bool, task: str = ""):
        self._busy = busy
        state = "disabled" if busy else "normal"
        for b in (self.btn_first_run, self.btn_update, self.btn_analyze,
                  self.btn_run, *self._db_buttons()):
            try:
                b.configure(state=state)
            except Exception:
                pass
        self.btn_stop.configure(state="normal" if busy else "disabled")
        self.progress.configure(mode="indeterminate" if busy else "determinate")
        if busy:
            self.progress.start()
            self.status_label.configure(text=f"⏳ {task}", text_color=ORANGE)
        else:
            self.progress.stop()
            self.progress.set(0)
            self._refresh_status()

    def _db_buttons(self):
        # собираем кнопки вкладки БД (для блокировки во время задач)
        return [w for w in self.winfo_children()] and []

    def _run_async(self, task_name: str, fn, on_done=None):
        """Запускает fn(progress_cb, cancel_cb) в рабочем потоке."""
        if self._busy:
            messagebox.showwarning("Занято", "Выполняется другая задача. Дождитесь окончания.")
            return
        self._cancel_event.clear()
        self._set_busy(True, task_name)
        self._log(f"▶ {task_name}…")

        def wrapper():
            try:
                result = fn(self._post_progress, self._cancel_event.is_set)
                self._queue.put(("done", task_name, result, on_done))
            except Exception as e:
                logger.exception("Ошибка задачи %s", task_name)
                self._queue.put(("error", task_name, str(e), None))

        self._worker = threading.Thread(target=wrapper, daemon=True)
        self._worker.start()

    def _post_progress(self, value, message: str = ""):
        """Из потока задачи: value — число 0..1 или строка-сообщение."""
        self._queue.put(("progress", value, message))

    def _process_queue(self):
        try:
            while True:
                item = self._queue.get_nowait()
                kind = item[0]
                if kind == "progress":
                    _, value, message = item
                    if isinstance(value, (int, float)):
                        self.progress.configure(mode="determinate")
                        self.progress.set(max(0.0, min(1.0, float(value))))
                    if message:
                        self.status_label.configure(text=f"⏳ {message}")
                        self._log(message)
                elif kind == "done":
                    _, name, result, on_done = item
                    self._set_busy(False)
                    self._log(f"✅ {name} завершено")
                    if on_done:
                        on_done(result)
                elif kind == "error":
                    _, name, err, _ = item
                    self._set_busy(False)
                    self._log(f"❌ {name}: {err}")
                    messagebox.showerror("Ошибка задачи", f"{name}:\n{err}")
        except queue.Empty:
            pass
        self.after(100, self._process_queue)

    def _refresh_status(self):
        stats = get_db_stats()
        if not stats["exists"]:
            txt, color = "🗄 БД нет — требуется первый запуск", ORANGE
        elif stats["stocks"] == 0:
            txt, color = "🗄 БД пуст — загрузите список акций", ORANGE
        else:
            txt = (f"🗄 БД: {stats['stocks']} тикеров, "
                   f"{stats['price_history']} котировок")
            color = GREEN
        self.status_label.configure(text=txt, text_color=color)

        # домашняя панель
        s = stats
        lines = [
            f"Файл БД: {DB_FILE.name} — {'✅ существует' if s['exists'] else '❌ отсутствует'}",
            f"Список акций (stocks): {s['stocks']}",
            f"История котировок (price_history): {s['price_history']}",
            f"Режим: {'первый запуск — нужна инициализация' if is_first_run() else 'штатный (данные есть)'}",
        ]
        self.home_status.configure(text="\n".join(lines))
        self._refresh_db_info()

    def _refresh_db_info(self):
        s = get_db_stats()
        size_kb = DB_FILE.stat().st_size / 1024 if DB_FILE.exists() else 0
        self.db_info.configure(text=(
            f"Файл: {DB_FILE}\n"
            f"Размер: {size_kb:,.0f} КБ\n"
            f"Тикеров (stocks): {s['stocks']}\n"
            f"Записей истории (price_history): {s['price_history']}"
        ))

    def _refresh_reports(self):
        for w in self._report_rows:
            w.destroy()
        self._report_rows.clear()
        files = sorted(REPORTS_DIR.glob("*.*"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not files:
            lbl = ctk.CTkLabel(self.reports_list, text="Отчётов пока нет — выполните анализ.",
                               text_color=ORANGE)
            lbl.grid(row=0, column=0, sticky="w", padx=8, pady=6)
            self._report_rows.append(lbl)
            return
        for i, f in enumerate(files[:60]):
            row = ctk.CTkFrame(self.reports_list, fg_color="transparent")
            row.grid(row=i, column=0, sticky="ew", padx=4, pady=2)
            row.grid_columnconfigure(0, weight=1)
            mtime = datetime.fromtimestamp(f.stat().st_mtime).strftime("%d.%m.%Y %H:%M")
            ctk.CTkLabel(row, text=f"📄 {f.name}", anchor="w").grid(row=0, column=0, sticky="w", padx=6)
            ctk.CTkLabel(row, text=mtime, text_color="gray").grid(row=0, column=1, padx=8)
            ctk.CTkButton(row, text="Открыть", width=80,
                          command=lambda p=str(f): open_path(p)).grid(row=0, column=2, padx=6)
            self._report_rows.append(row)

    def on_save_report_copy(self):
        dst = filedialog.askdirectory(title="Куда сохранить копию отчёта?")
        if not dst:
            return
        files = sorted(REPORTS_DIR.glob("*.xlsx"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not files:
            messagebox.showinfo("Нет файлов", "В папке reports нет ни одного отчёта.")
            return
        import shutil
        shutil.copy2(files[0], os.path.join(dst, files[0].name))
        self._log(f"Копия отчёта сохранена: {files[0].name} → {dst}")

    # ------------------------------------------------------------------ actions

    def on_first_run(self):
        """Первый запуск: схема БД + тикеры + история для небольшого набора."""

        def task(progress, cancel):
            from analysis.core.db_manager import DatabaseManager
            from analysis.core.history_updater import PriceHistoryUpdater

            dbm = DatabaseManager()
            progress(0.05, "Создание схемы базы данных…")
            dbm.create_schema()

            progress(0.1, "Загрузка списка акций с MOEX ISS API…")
            count = dbm.load_tickers_from_moex()
            progress(0.3, f"Загружено тикеров: {count}. Старт загрузки истории…")

            up = PriceHistoryUpdater()
            limit = self._ticker_limit()
            tickers = None if limit == 0 else [
                t["ticker"] for t in up._get_tickers(None)[:limit]]
            days = int(self.var_histdays.get())

            def pcb(i, total, msg):
                if cancel():
                    raise InterruptedError("Отменено пользователем")
                progress(0.3 + 0.7 * i / max(total, 1), msg)

            res = up.update_all(tickers=tickers, days=days, progress_cb=pcb,
                                cancel_cb=cancel)
            progress(1.0, "Первичная загрузка завершена")
            return res

        def done(res):
            self._log(f"Инициализация завершена: обновлено {res['updated']} тикеров, "
                      f"{res['records']} записей истории")
            messagebox.showinfo(
                "Первый запуск",
                f"Готово!\n\nТикеров: {res['updated']}\n"
                f"Записей котировок: {res['records']}\n"
                f"Ошибок: {len(res['errors'])}\n\n"
                "Можно переходить к анализу на вкладке «⚙️ Анализ».")

        self._run_async("Первый запуск (инициализация)", task, done)

    def on_init_db(self):
        def task(progress, cancel):
            from analysis.core.db_manager import DatabaseManager
            progress(0.2, "Создание/проверка схемы БД…")
            DatabaseManager().create_schema()
            progress(1.0, "Схема готова")
            return True

        def done(_):
            messagebox.showinfo("БД", "Схема базы данных создана/проверена.")

        self._run_async("Создание схемы БД", task, done)

    def on_load_tickers(self):
        def task(progress, cancel):
            from analysis.core.db_manager import DatabaseManager
            progress(0.1, "Запрос списка акций к MOEX ISS API…")
            n = DatabaseManager().load_tickers_from_moex()
            progress(1.0, f"Загружено тикеров: {n}")
            return n

        def done(n):
            messagebox.showinfo("Тикеры", f"Список акций обновлён: {n} тикеров.")

        self._run_async("Загрузка списка акций", task, done)

    def _ticker_limit(self) -> int:
        try:
            return max(0, int(self.ent_limit.get()))
        except (ValueError, AttributeError):
            return 0

    def on_update_history(self):
        if not DB_FILE.exists() or get_db_stats()["stocks"] == 0:
            if messagebox.askyesno(
                    "Нет данных",
                    "База данных не инициализирована.\n\n"
                    "Выполнить первый запуск (создать БД + загрузить акции)?"):
                return self.on_first_run()
            return

        def task(progress, cancel):
            from analysis.core.history_updater import PriceHistoryUpdater
            up = PriceHistoryUpdater()
            limit = self._ticker_limit()
            tickers = None if limit == 0 else [
                t["ticker"] for t in up._get_tickers(None)[:limit]]
            days = int(self.var_histdays.get())

            def pcb(i, total, msg):
                if cancel():
                    raise InterruptedError("Отменено пользователем")
                progress(i / max(total, 1), msg)

            res = up.update_all(tickers=tickers, days=days, progress_cb=pcb,
                                cancel_cb=cancel)
            progress(1.0, "Обновление истории завершено")
            return res

        def done(res):
            self._log(f"История: обновлено {res['updated']}, пропущено {res['skipped']}, "
                      f"записей {res['records']}, ошибок {len(res['errors'])}")
            messagebox.showinfo(
                "Обновление данных",
                f"Обновлено тикеров: {res['updated']}\n"
                f"Записей котировок: {res['records']}\n"
                f"Пропущено: {res['skipped']}\nОшибок: {len(res['errors'])}")

        self._run_async("Обновление истории котировок", task, done)

    def _collect_params(self) -> dict:
        days_raw = self.ent_days.get().replace(" ", "")
        try:
            days = sorted({int(d) for d in days_raw.split(",") if d})
        except ValueError:
            raise ValueError("Некорректный список дней прогноза. Пример: 1,7,14,30")
        stock_type = {"Все": 1, "Обыкновенные": 2, "Привилегированные": 3}[
            self.var_stocktype.get()]
        mode = int(self.var_mode.get().split(" ")[0])
        return {
            "top_n": int(self.var_topn.get()),
            "stock_type": stock_type,
            "mode": mode,
            "prediction_days": days or [1, 7, 14, 30],
            "min_confidence": round(self.slider_conf.get() / 100.0, 2),
        }

    def on_run_analysis(self, quick: bool = False):
        try:
            params = self._collect_params()
        except ValueError as e:
            messagebox.showerror("Параметры", str(e))
            return

        if not DB_FILE.exists() or get_db_stats()["stocks"] == 0:
            if messagebox.askyesno(
                    "Нет данных",
                    "Для анализа нужны данные в базе.\n\n"
                    "Выполнить первый запуск сейчас (создать БД + загрузить акции)?"):
                return self.on_first_run()
            return

        def task(progress, cancel):
            from analysis.main import run_analysis_programmatically

            def wrapped(msg):
                if cancel():
                    raise InterruptedError("Отменено пользователем")
                progress(-1, str(msg))  # indeterminate-style сообщения

            results, files = run_analysis_programmatically(params, progress_cb=wrapped)
            progress(1.0, "Анализ завершён")
            return results, files

        def done(payload):
            results, files = payload
            self.results_area.delete("1.0", "end")
            if not results:
                self.results_area.insert("end", "Нет результатов анализа.\n")
            else:
                header = (f"{'№':>3} {'ТИКЕР':<8} {'РОСТ%':>8} {'УВЕР.%':>7} "
                          f"{'ЦЕНА':>12}  НАЗВАНИЕ\n" + "─" * 70 + "\n")
                self.results_area.insert("end", header)
                for i, r in enumerate(results, 1):
                    self.results_area.insert("end", (
                        f"{i:>3} {r.get('ticker',''):<8} "
                        f"{r.get('avg_change_percent',0):>+8.2f} "
                        f"{r.get('avg_confidence',0)*100:>7.1f} "
                        f"{r.get('last_price',0):>12.2f}  "
                        f"{(r.get('name') or '')[:38]}\n"))
            self._refresh_reports()
            msg = f"Проанализировано: {len(results)}\n\nОтчёты:\n" + \
                  ("\n".join(f"{k}: {os.path.basename(v)}" for k, v in files.items())
                   or "не созданы")
            messagebox.showinfo("Анализ завершён", msg)

        self._run_async("Полный анализ рынка", task, done)

    def on_cancel(self):
        self._cancel_event.set()
        self._log("⏹ Запрошена остановка текущей задачи…")

    def on_check_connection(self):
        def task(progress, cancel):
            from analysis.core.moex_client import WorkingMOEXClient
            progress(0.3, "Тест соединения с iss.moex.com…")
            client = WorkingMOEXClient()
            info = client.validate_ticker("SBER")
            progress(1.0, "Проверка соединения выполнена")
            return info

        def done(info):
            ok = bool(info and info.get("valid"))
            self._log("MOEX API: " + ("✅ доступен (SBER найден)" if ok else f"⚠ ответ: {info}"))
            messagebox.showinfo(
                "Соединение",
                "MOEX ISS API доступен ✅" if ok else
                f"Проблема с MOEX ISS API:\n{info}")

        self._run_async("Проверка соединения с MOEX", task, done)

    def on_full_check(self):
        self.checks_area.delete("1.0", "end")

        def check(name, fn):
            try:
                res = fn()
                self._check_msg(f"✅ {name}: {res}")
            except Exception as e:
                self._check_msg(f"❌ {name}: {e}")

        def task(progress, cancel):
            import importlib
            progress(0.1, "Проверка окружения и модулей…")

            out = []

            def ver(mod):
                m = importlib.import_module(mod)
                return getattr(m, "__version__", "?")

            checks = [
                ("Python", lambda: sys.version.split()[0]),
                ("pandas", lambda: ver("pandas")),
                ("numpy", lambda: ver("numpy")),
                ("scikit-learn", lambda: ver("sklearn")),
                ("openpyxl", lambda: ver("openpyxl")),
                ("customtkinter", lambda: ver("customtkinter")),
            ]
            for name, fn in checks:
                try:
                    out.append(f"✅ {name}: {fn()}")
                except Exception as e:
                    out.append(f"❌ {name}: {e}")

            # БД
            s = get_db_stats()
            out.append(f"{'✅' if s['exists'] else '❌'} База данных: "
                       f"{DB_FILE} (тикеров: {s['stocks']}, котировок: {s['price_history']})")

            # MOEX
            try:
                from analysis.core.moex_client import WorkingMOEXClient
                info = WorkingMOEXClient().validate_ticker("SBER")
                out.append(f"{'✅' if info.get('valid') else '⚠'} MOEX ISS API: "
                           f"SBER valid={info.get('valid')}")
            except Exception as e:
                out.append(f"❌ MOEX ISS API: {e}")

            # Модели
            try:
                from analysis.models.model_manager import ModelManager
                out.append("✅ Модельный слой импортируется")
            except Exception as e:
                out.append(f"⚠ Модельный слой: {e}")

            progress(1.0, "Диагностика завершена")
            return out

        def done(lines):
            for ln in lines:
                self._check_msg(ln)
            self._log("Диагностика завершена — см. вкладку «🧪 Проверка»")

        self._run_async("Полная диагностика", task, done)


def run_gui() -> int:
    """Точка входа GUI (используется analysis/main.py и корнем main.py)."""
    app = App()
    app.mainloop()
    return 0
