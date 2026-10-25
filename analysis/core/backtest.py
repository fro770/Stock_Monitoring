"""
Самопроверка системы: walk-forward бэктест на исторических данных.

Идея (как просил пользователь): скрипт делает СОТНИ предсказаний «из прошлого»,
где исход уже известен, и по результатам:
  1) считает точность направления (hit-rate), MAE/MAPE прогноза цены,
     «навык» относительно наивного прогнозирования (skill score);
  2) проверяет калибровку уверенности (Brier score + соответствие заявленной
     вероятности фактической доле попаданий);
  3) пересчитывает ВЕСА моделей (через softmax от hit-rate каждой модели) и
     параметры калибровки уверенности — т.е. занимается САМОКОРРЕКТИРОВАНИЕМ;
  4) пишет отчёт JSON + MD и обновляет data/model_weights.json.

Реализация без заглядывания в будущее: для даты T модель видит только данные
до T включительно; исход = цена через horizon торговых дней после T.
"""

import json
import logging
import os
import time
from datetime import datetime
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from .config import Config
from ..models.base_predictor import BasePredictor
from ..models.trend_predictor import TrendPredictor
from ..models.finrl_predictor import FinRLPredictor
from ..models.stat_predictors import ARSMPredictor, MeanReversionPredictor
from ..models.weights_store import WeightStore

logger = logging.getLogger(__name__)


class _NaivePredictor(BasePredictor):
    """Бенчмарк: цена не изменится (для расчёта skill score)."""

    def __init__(self):
        super().__init__("naive")

    def predict(self, ticker, data, days_ahead):
        last = float(data['close_price'].iloc[-1])
        return {'price': last, 'change_percent': 0.0,
                'confidence': 0.5, 'model': 'naive'}


def build_model_pool(mode: int = 3) -> List[BasePredictor]:
    """Пулы моделей для бэктеста: все доступные предикторы оцениваются раздельно."""
    pool = [TrendPredictor(), ARSMPredictor()]
    if mode >= 2:
        try:
            from ..models.ml_predictor import MLPredictor
            pool.append(MLPredictor())
        except Exception:
            pass
    if mode >= 3:
        pool.append(FinRLPredictor())
        pool.append(MeanReversionPredictor())
    return pool


class BacktestRunner:
    """Запуск самотестирования на истории из price_history."""

    def __init__(self, horizons: List[int] = None, n_predictions: int = 300,
                 min_history: int = 120, mode: int = 3, seed: int = 42,
                 tickers: List[str] = None, apply_weights: bool = True,
                 progress_cb: Optional[callable] = None,
                 use_stored_weights: bool = False):
        """
        Args:
            horizons: горизонты прогноза в днях (по умолчанию [3,7,14,30])
            n_predictions: сколько всего предсказаний сделать (сотни)
            min_history: минимум баров истории перед датой прогноза
            mode: режим ансамбля (влияет на пул моделей)
            apply_weights: применять ли найденные веса к живому ансамблю
            tickers: ограничить список тикеров (для быстрых тестов)
            use_stored_weights: оценивать ансамбль с текущими сохранёнными
                весами из model_weights.json (по умолчанию — нейтральные веса,
                чтобы измерять модели, а не старые веса)
        """
        self.horizons = horizons or [3, 7, 14, 30]
        self.n_predictions = max(int(n_predictions), len(self.horizons))
        self.min_history = min_history
        self.mode = mode
        self.seed = seed
        self.tickers_filter = tickers
        self.apply_weights = apply_weights
        self.use_stored_weights = use_stored_weights
        self.progress_cb = progress_cb or (lambda m: None)

        rng = np.random.default_rng(seed)
        self.rng = rng
        self.pool = build_model_pool(mode)
        self.naive = _NaivePredictor()
        self.store = WeightStore()

    # ------------------------------------------------------------- данные ---

    def _load_history(self) -> Dict[str, pd.DataFrame]:
        import sqlite3
        if not os.path.exists(Config.DB_PATH):
            raise RuntimeError("Нет базы данных data/stocks.db — сначала выполните первый запуск.")
        conn = sqlite3.connect(Config.DB_PATH)
        where = ""
        params = ()
        if self.tickers_filter:
            where = f"WHERE ticker IN ({','.join('?' * len(self.tickers_filter))})"
            params = tuple(self.tickers_filter)
        df = pd.read_sql_query(
            f"SELECT ticker, date, open, high, low, close, volume FROM price_history {where}",
            conn, params=params)
        conn.close()
        if df.empty:
            raise RuntimeError("В таблице price_history нет данных — выполните обновление истории.")
        out = {}
        for t, g in df.groupby('ticker'):
            g = g.sort_values('date').reset_index(drop=True)
            g['Date'] = pd.to_datetime(g['date'])
            g['close_price'] = g['close'].astype(float)
            g['volume'] = g['volume'].astype(float)
            if len(g) >= self.min_history + max(self.horizons) + 10:
                out[t] = g[['Date', 'open', 'high', 'low', 'close_price', 'volume']]
        return out

    # --------------------------------------------------------------- прогон ---

    def run(self) -> Dict:
        t0 = time.time()
        self.progress_cb("🔁 Самопроверка: загрузка истории из БД...")
        histories = self._load_history()
        if not histories:
            raise RuntimeError("Недостаточно истории ни у одного тикера для бэктеста "
                               f"(нужно ≥{self.min_history} баров).")

        # план прогонов: равномерно по тикерам и датам
        per_ticker = max(1, self.n_predictions // len(histories))
        plan = []
        for t, h in sorted(histories.items()):
            n = len(h)
            first = self.min_history
            last = n - max(self.horizons) - 1
            if last <= first:
                continue
            idxs = np.unique(np.linspace(first, last, per_ticker).astype(int))
            for i in idxs:
                plan.append((t, int(i)))
        # если тикеров мало — добавляем больше дат, чтобы выйти на сотни предсказаний
        while len(plan) < self.n_predictions and histories:
            extra_needed = self.n_predictions - len(plan)
            denser = max(per_ticker * 2, per_ticker + extra_needed // len(histories) + 1)
            plan = []
            for t, h in sorted(histories.items()):
                n = len(h)
                first = self.min_history
                last = n - max(self.horizons) - 1
                if last <= first:
                    continue
                idxs = np.unique(np.linspace(first, last, denser).astype(int))
                for i in idxs:
                    plan.append((t, int(i)))
            if denser > 500:
                break
        plan = plan[: self.n_predictions]

        self.progress_cb(f"🔁 План: {len(plan)} предсказаний по {len(set(t for t,_ in plan))} тикерам ...")

        records = []          # плоские строки для отчётов
        model_stats = {}      # name -> counters
        ensemble_stats = {}   # horizon -> counters
        calib_rows = []       # (conf, hit) для проверки калибровки

        # живой ансамбль (тот же код, что в проде) — по умолчанию с нейтральными
        # весами, иначе мы измеряли бы старые веса, а не модели
        from ..models.ensemble import EnsemblePredictor
        if self.use_stored_weights:
            ens = EnsemblePredictor(mode=self.mode)  # веса из model_weights.json
        else:
            neutral_store = WeightStore(path=os.path.join(Config.DATA_DIR, "_neutral_weights.json"))
            neutral_store.data = {'global_weights': {}, 'horizon_weights': {},
                                  'per_ticker_weights': {}, 'calibration': {'slope': 1.0, 'intercept': 0.0}}
            ens = EnsemblePredictor(mode=self.mode, weight_store=neutral_store)

        total = len(plan)
        for k, (ticker, i) in enumerate(plan):
            h = histories[ticker]
            train_slice = h.iloc[: i + 1].reset_index(drop=True)
            row = h.iloc[i]
            date = row['Date']
            base_price = float(row['close_price'])

            for horizon in self.horizons:
                j = i + horizon
                if j >= len(h):
                    continue
                actual_price = float(h.iloc[j]['close_price'])
                actual_ret = actual_price / base_price - 1

                preds_by_model = {}
                for mp in self.pool:
                    try:
                        pr = mp.predict(ticker, train_slice, horizon)
                        if pr and 'error' not in pr:
                            preds_by_model[mp.name] = pr
                    except Exception:
                        pass
                try:
                    ens_pred = ens.predict(ticker, train_slice, horizon)
                except Exception:
                    ens_pred = None

                naive_pred = self.naive.predict(ticker, train_slice, horizon)

                # статистика по каждой модели
                for name, pr in preds_by_model.items():
                    st = model_stats.setdefault(name, {'n': 0, 'hits': 0, 'mae': 0.0,
                                                       'sum_conf': 0.0, 'brier': 0.0})
                    pred_ret = float(pr.get('change_percent', 0)) / 100.0
                    hit = int(np.sign(pred_ret) == np.sign(actual_ret)) if pred_ret != 0 else 0
                    st['n'] += 1
                    st['hits'] += hit
                    st['mae'] += abs(pred_ret - actual_ret)
                    conf = float(pr.get('confidence', 0.5))
                    st['sum_conf'] += conf
                    st['brier'] += (conf - hit) ** 2
                    calib_rows.append((name, conf, hit))

                # статистика ансамбля по горизонтам
                if ens_pred and 'error' not in ens_pred:
                    st = ensemble_stats.setdefault(horizon, {'n': 0, 'hits': 0, 'mae': 0.0,
                                                             'naive_mae': 0.0, 'sum_conf': 0.0})
                    pred_ret = float(ens_pred.get('change_percent', 0)) / 100.0
                    hit = int(np.sign(pred_ret) == np.sign(actual_ret)) if pred_ret != 0 else 0
                    st['n'] += 1
                    st['hits'] += hit
                    st['mae'] += abs(pred_ret - actual_ret)
                    st['naive_mae'] += abs(0.0 - actual_ret)
                    st['sum_conf'] += float(ens_pred.get('confidence', 0.5))
                    calib_rows.append(('ensemble', float(ens_pred.get('confidence', 0.5)), hit))

                records.append({
                    'ticker': ticker, 'date': str(date)[:10], 'horizon': horizon,
                    'base_price': round(base_price, 4),
                    'actual_price': round(actual_price, 4),
                    'actual_change_pct': round(actual_ret * 100, 3),
                    'pred_change_pct': round(float((ens_pred or {}).get('change_percent', 0)), 3),
                    'pred_confidence': round(float((ens_pred or {}).get('confidence', 0)), 3),
                    'direction_hit': int(np.sign(float((ens_pred or {}).get('change_percent', 0))) ==
                                         np.sign(actual_ret)) if ens_pred else 0,
                    'per_model': {nm: round(float(p.get('change_percent', 0)), 3)
                                  for nm, p in preds_by_model.items()},
                })

            if (k + 1) % 25 == 0 or k == total - 1:
                self.progress_cb(f"🔁 Прогресс бэктеста: {k + 1}/{total} окон ({time.time()-t0:.0f}s)")

        summary = self._summarize(model_stats, ensemble_stats, calib_rows, records, t0)
        return summary

    # ------------------------------------------------------------ метрики ---

    def _summarize(self, model_stats, ensemble_stats, calib_rows, records, t0) -> Dict:
        def rate(st):
            n = st['n'] or 1
            return st['hits'] / n

        models_report = {}
        for name, st in model_stats.items():
            n = max(st['n'], 1)
            models_report[name] = {
                'predictions': st['n'],
                'direction_accuracy': round(rate(st), 4),
                'avg_confidence': round(st['sum_conf'] / n, 4),
                'mae_return': round(st['mae'] / n, 5),
                'brier_score': round(st['brier'] / n, 4),
            }

        horizons_report = {}
        tot_n = tot_hits = 0
        tot_mae = tot_naive = 0.0
        for hz, st in ensemble_stats.items():
            n = max(st['n'], 1)
            acc = st['hits'] / n
            mae = st['mae'] / n
            naive_mae = st['naive_mae'] / n
            skill = 1 - mae / naive_mae if naive_mae > 0 else 0.0
            horizons_report[hz] = {
                'predictions': st['n'],
                'direction_accuracy': round(acc, 4),
                'mae_return': round(mae, 5),
                'naive_mae_return': round(naive_mae, 5),
                'skill_vs_naive': round(skill, 4),
                'avg_confidence': round(st['sum_conf'] / n, 4),
            }
            tot_n += st['n']; tot_hits += st['hits']
            tot_mae += st['mae']; tot_naive += st['naive_mae']

        overall_acc = tot_hits / tot_n if tot_n else 0.0
        overall_mae = tot_mae / tot_n if tot_n else 0.0
        naive_mae = tot_naive / tot_n if tot_n else 0.0
        skill = 1 - overall_mae / naive_mae if naive_mae > 0 else 0.0

        # ---- калибровка уверенности: биннинг по 10 корзинам ----
        calibration_bins = []
        if calib_rows:
            confs = np.array([c for _, c, _ in calib_rows], dtype=float)
            hits = np.array([h for _, _, h in calib_rows], dtype=float)
            edges = np.linspace(0, 1, 11)
            for a, b in zip(edges[:-1], edges[1:]):
                mask = (confs >= a) & (confs < b + (1e-9 if b == 1 else 0))
                if mask.sum() >= 5:
                    calibration_bins.append({
                        'bin': f"{a:.1f}-{b:.1f}",
                        'count': int(mask.sum()),
                        'predicted_avg': round(float(confs[mask].mean()), 4),
                        'actual_accuracy': round(float(hits[mask].mean()), 4),
                    })

        # ---- самокоррекция весов ----
        new_global, notes = self._compute_new_weights(models_report, overall_acc)

        result = {
            'meta': {
                'timestamp': datetime.now().isoformat(),
                'mode': self.mode,
                'horizons': self.horizons,
                'requested_predictions': self.n_predictions,
                'executed_predictions': len(records),
                'tickers_used': sorted({r['ticker'] for r in records}),
                'duration_sec': round(time.time() - t0, 1),
                'min_history_bars': self.min_history,
            },
            'overall': {
                'direction_accuracy': round(overall_acc, 4),
                'mae_return': round(overall_mae, 5),
                'naive_mae_return': round(naive_mae, 5),
                'skill_vs_naive': round(skill, 4),
                'total_predictions': tot_n,
            },
            'by_horizon': horizons_report,
            'by_model': models_report,
            'calibration_bins': calibration_bins,
            'recommended_weights': new_global,
            'notes': notes,
        }
        return result

    def _compute_new_weights(self, models_report: Dict, overall_acc: float):
        """Пересчёт весов моделей: softmax от (hit-rate − 0.5) + рекомендации."""
        notes = []
        names = list(models_report.keys())
        if not names:
            return {}, ["Нет смоделированных прогнозов — веса не изменены."]
        scores = np.array([models_report[n]['direction_accuracy'] - 0.5 for n in names])
        temp = 0.15
        w = np.exp(scores / temp)
        w = w / w.sum() * len(names)  # среднее = 1.0
        w = np.clip(w, 0.2, 2.5)
        new_global = {n: round(float(v), 3) for n, v in zip(names, w)}

        for n, rep in models_report.items():
            acc = rep['direction_accuracy']
            conf = rep['avg_confidence']
            if acc < 0.45:
                notes.append(f"⚠ Модель «{n}»: точность направления {acc:.1%} ниже случайной "
                             f"(50%) — вес снижен до {new_global[n]}. Рекомендую проверить её "
                             f"гиперпараметры или исключить из ансамбля.")
            elif conf - acc > 0.15:
                notes.append(f"⚠ Модель «{n}»: переоценённая уверенность (conf {conf:.1%} vs "
                             f"точность {acc:.1%}) — параметр slope калибровки уменьшен.")
            elif acc - conf > 0.10:
                notes.append(f"ℹ Модель «{n}»: недооценённая уверенность (conf {conf:.1%} vs "
                             f"точность {acc:.1%}) — можно поднять intercept калибровки.")
            else:
                notes.append(f"✅ Модель «{n}»: уверенность согласована с точностью "
                             f"({conf:.1%} vs {acc:.1%}).")

        return new_global, notes

    # --------------------------------------------------------- сохранение ---

    def save_reports(self, summary: Dict) -> Dict[str, str]:
        os.makedirs(Config.REPORTS_DIR, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        jpath = os.path.join(Config.REPORTS_DIR, f"backtest_{ts}.json")
        mpath = os.path.join(Config.REPORTS_DIR, f"backtest_{ts}.md")
        with open(jpath, 'w', encoding='utf-8') as f:
            json.dump(summary, f, ensure_ascii=False, indent=2, default=str)
        with open(mpath, 'w', encoding='utf-8') as f:
            f.write(self._render_markdown(summary))
        return {'json': jpath, 'md': mpath}

    def apply_corrections(self, summary: Dict):
        """Самокоррекция: сохраняет новые веса и калибровку в model_weights.json."""
        store = WeightStore()
        store.set_global_weights(summary.get('recommended_weights', {}))
        # калибровка: приводим среднюю уверенность к средней точности
        ov = summary['overall']
        avg_conf = np.mean([h['avg_confidence'] for h in summary['by_horizon'].values()] or [0.5])
        target = ov['direction_accuracy']
        if avg_conf > 0:
            slope = float(np.clip(target / avg_conf, 0.5, 1.6))
        else:
            slope = 1.0
        store.set_calibration(slope=slope, intercept=0.0)
        store.append_history({
            'timestamp': summary['meta']['timestamp'],
            'executed': summary['meta']['executed_predictions'],
            'direction_accuracy': ov['direction_accuracy'],
            'skill_vs_naive': ov['skill_vs_naive'],
            'calibration_slope': round(slope, 4),
            'weights': summary.get('recommended_weights', {}),
        })
        store.save()
        # чистим временный файл нейтральных весов
        tmp = os.path.join(Config.DATA_DIR, "_neutral_weights.json")
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass
        return store.path

    @staticmethod
    def _render_markdown(s: Dict) -> str:
        ov = s['overall']
        lines = [
            "# 📊 Отчёт самопроверки (walk-forward бэктест)",
            "",
            f"- Дата прогона: {s['meta']['timestamp']}",
            f"- Предсказаний выполнено: **{ov['total_predictions']}** "
            f"(тикеров: {len(s['meta']['tickers_used'])}, горизонты: {s['meta']['horizons']})",
            f"- Длительность: {s['meta']['duration_sec']} сек",
            "",
            "## Итоговая точность",
            f"- Точность направления: **{ov['direction_accuracy']:.1%}**",
            f"- MAE прогноза доходности: {ov['mae_return']:.4f}",
            f"- Наивный MAE (цена не меняется): {ov['naive_mae_return']:.4f}",
            f"- Навык против наивного (skill): **{ov['skill_vs_naive']:+.1%}**",
            "",
            "## По горизонтам",
            "| Горизонт | Предск. | Точность напр. | MAE | Skill | Ср. уверенность |",
            "|---|---|---|---|---|---|",
        ]
        for hz, rep in s['by_horizon'].items():
            lines.append(f"| {hz} дн | {rep['predictions']} | {rep['direction_accuracy']:.1%} "
                         f"| {rep['mae_return']:.4f} | {rep['skill_vs_naive']:+.1%} "
                         f"| {rep['avg_confidence']:.1%} |")
        lines += ["", "## По моделям",
                  "| Модель | Предск. | Точность | Уверенность | MAE | Brier |",
                  "|---|---|---|---|---|---|"]
        for nm, rep in s['by_model'].items():
            lines.append(f"| {nm} | {rep['predictions']} | {rep['direction_accuracy']:.1%} "
                         f"| {rep['avg_confidence']:.1%} | {rep['mae_return']:.4f} "
                         f"| {rep['brier_score']:.3f} |")
        if s.get('calibration_bins'):
            lines += ["", "## Калибровка уверенности",
                      "| Корзина | Кол-во | Заявленная вер. | Фактическая доля |",
                      "|---|---|---|---|"]
            for b in s['calibration_bins']:
                lines.append(f"| {b['bin']} | {b['count']} | {b['predicted_avg']:.2f} "
                             f"| {b['actual_accuracy']:.2f} |")
        lines += ["", "## Новые веса моделей (применены автоматически)",
                  "```json", json.dumps(s.get('recommended_weights', {}),
                                        ensure_ascii=False, indent=2), "```",
                  "", "## Выводы и рекомендации"]
        for n in s.get('notes', []):
            lines.append(f"- {n}")
        return "\n".join(lines) + "\n"


# --------- служебное: прокинуть калибровочные бины в _compute_new_weights --
def _attach_bins(runner_cls: type):
    orig_summarize = runner_cls._summarize

    def summarize(self, model_stats, ensemble_stats, calib_rows, records, t0):
        self._last_calibration_bins = None
        res = orig_summarize(self, model_stats, ensemble_stats, calib_rows, records, t0)
        self._last_calibration_bins = res.get('calibration_bins')
        return res

    runner_cls._summarize = summarize


BacktestRunner._last_calibration_bins = None
_attach_bins(BacktestRunner)


def run_self_check(n_predictions: int = 300, horizons=None, mode: int = 3,
                   tickers=None, apply_fixes: bool = True, progress_cb=None,
                   use_stored_weights: bool = False) -> Dict:
    """Публичная функция для GUI/CLI: прогнать бэктест, вывести %, исправить веса."""
    runner = BacktestRunner(horizons=horizons, n_predictions=n_predictions,
                            mode=mode, tickers=tickers, progress_cb=progress_cb,
                            use_stored_weights=use_stored_weights)
    summary = runner.run()
    files = runner.save_reports(summary)
    summary['report_files'] = files
    if apply_fixes:
        weights_path = runner.apply_corrections(summary)
        summary['weights_updated_in'] = weights_path
    return summary
