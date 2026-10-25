#!/usr/bin/env python3
"""
Запуск самопроверки (walk-forward бэктеста) из командной строки.

Делает сотни предсказаний на исторических датах, где исход уже известен,
считает точность/калибровку уверенности и (по умолчанию) автоматически
корректирует веса моделей в data/model_weights.json.

Примеры:
    python analysis/scripts/run_backtest.py                     # 300 предсказаний, все модели
    python analysis/scripts/run_backtest.py -n 500 --mode 1     # быстрый режим (только trend+AR)
    python analysis/scripts/run_backtest.py --tickers SBER,GAZP,LKOH -n 200
    python analysis/scripts/run_backtest.py --horizons 3,7 --dry-run   # без записи весов

Требования: заполненная БД data/stocks.db (первый запуск проекта или кнопка
«🚀 Первый запуск» / «Обновить историю» во вкладке «База данных»).
"""

import argparse
import logging
import os
import sys

# Корень проекта -> импорты пакетов работают при запуске из любой директории
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
os.chdir(PROJECT_ROOT)


def parse_args():
    p = argparse.ArgumentParser(
        description="Самопроверка системы прогноза: walk-forward бэктест с сотнями предсказаний.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    p.add_argument("-n", "--predictions", type=int, default=300,
                   help="сколько всего предсказаний сделать")
    p.add_argument("--horizons", type=str, default="3,7,14,30",
                   help="горизонты прогноза в днях, через запятую")
    p.add_argument("--mode", type=int, default=3, choices=[1, 2, 3],
                   help="пул моделей: 1=trend+AR, 2=+ML, 3=+FinRL/MeanReversion")
    p.add_argument("--tickers", type=str, default="",
                   help="ограничить тикеры списком через запятую (напр. SBER,GAZP)")
    p.add_argument("--min-history", type=int, default=120,
                   help="минимум баров истории перед датой прогноза")
    p.add_argument("--seed", type=int, default=42, help="зерно выборки дат")
    p.add_argument("--use-stored-weights", action="store_true",
                   help="оценивать ансамбль с текущими сохранёнными весами из "
                        "data/model_weights.json (по умолчанию — нейтральные веса, "
                        "чтобы измерять модели, а не старые веса)")
    p.add_argument("--dry-run", action="store_true",
                   help="только отчёт: НЕ применять скорректированные веса к живому ансамблю")
    return p.parse_args()


def main():
    args = parse_args()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s | %(levelname)-7s | %(name)s: %(message)s",
                        datefmt="%H:%M:%S")

    try:
        horizons = [int(x) for x in args.horizons.split(",") if x.strip()]
        assert horizons
    except Exception:
        print("❌ Неверный формат --horizons, пример: --horizons 3,7,14")
        sys.exit(2)

    tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()] or None

    from analysis.core.backtest import run_self_check

    def progress(msg):
        print(f"  {msg}")

    print("=" * 70)
    print("  🧪 САМОПРОВЕРКА (backtest): {} предсказаний, горизонты {}, режим {}".format(
        args.predictions, horizons, args.mode))
    if tickers:
        print(f"  Тикеры: {', '.join(tickers)}")
    print("=" * 70)

    try:
        summary = run_self_check(
            n_predictions=args.predictions,
            horizons=horizons,
            mode=args.mode,
            tickers=tickers,
            apply_fixes=not args.dry_run,
            progress_cb=progress,
            use_stored_weights=args.use_stored_weights,
        )
    except RuntimeError as e:
        print(f"\n❌ {e}")
        print("➤ КАК ИСПРАВИТЬ: убедитесь, что БД заполнена — запустите `python main.py` "
              "и выполните «Первый запуск» (или обновите историю во вкладке «База данных»).")
        sys.exit(1)

    s = summary.get("overall", summary)
    print("\n" + "-" * 70)
    print(f"  Предсказаний выполнено : {s.get('total_predictions')}")
    print(f"  Точность направления   : {s.get('direction_accuracy', 0):.1%}")
    print(f"  Skill vs naive         : {s.get('skill_vs_naive', 0):+.1%}")
    print(f"  Средняя уверенность    : {s.get('avg_confidence', 0):.1%}")
    print(f"  Brier score            : {s.get('brier_score', float('nan')):.3f}")
    print(f"  Время прогона          : {s.get('elapsed_sec', 0):.1f} c")

    by_model = s.get("by_model") or {}
    if by_model:
        print("\n  По моделям:")
        for name, rep in by_model.items():
            print(f"    {name:<18} точность {rep['direction_accuracy']:.1%} "
                  f"(уверенность {rep['avg_confidence']:.1%}, {rep['predictions']} предск.)")

    w = summary.get("recommended_weights")
    if w:
        print(f"\n  Рекомендуемые веса моделей: {w}")
        if args.dry_run:
            print("  (--dry-run: веса НЕ записаны)")
        else:
            print(f"  ✔ Веса сохранены: {summary.get('weights_updated_in', 'data/model_weights.json')}")

    files = summary.get("report_files") or {}
    if files:
        print("\n  Отчёты:")
        for kind, path in files.items():
            print(f"    {kind}: {path}")

    notes = summary.get("notes") or []
    if notes:
        print("\n  Рекомендации:")
        for n in notes:
            print(f"    • {n}")
    print("-" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
