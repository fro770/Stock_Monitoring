"""
Ансамбль моделей прогноза (v2): до 5 моделей + обучаемые веса из WeightStore.

Режимы:
 1 (быстрый)   — trend + ar_garch (лёгкие, без sklearn-обучения на каждом тикере);
 2 (стандарт)  — + ml_ensemble;
 3 (глубокий)  — + finrl + mean_reversion, полные детали индивидуальных прогнозов.

Комбинирование: взвешенное среднее прогнозов, где вес_i = store_weight * confidence_i.
Итоговая уверенность = согласованность направлений (мягкое голосование с учётом
весов) × средняя калиброванная уверенность. Веса берутся из data/model_weights.json,
который обновляется бэктестом (самопроверкой).
"""

import numpy as np
import pandas as pd
from typing import Dict

from .base_predictor import BasePredictor
from .trend_predictor import TrendPredictor
from .finrl_predictor import FinRLPredictor
from .ml_predictor import MLPredictor
from .stat_predictors import ARSMPredictor, MeanReversionPredictor
from .weights_store import WeightStore


class EnsemblePredictor(BasePredictor):
    """Взвешенный самообучаемый ансамбль предсказателей."""

    def __init__(self, mode: int = 2, weight_store: WeightStore = None):
        super().__init__("ensemble")
        self.mode = mode
        self.store = weight_store or WeightStore()
        self.predictors = []
        self._init_predictors()

    def _init_predictors(self):
        # Всегда: технический тренд и статистическая модель
        self.predictors.append(TrendPredictor())
        self.predictors.append(ARSMPredictor())

        if self.mode >= 2:
            self.predictors.append(MLPredictor())

        if self.mode >= 3:
            self.predictors.append(FinRLPredictor())
            self.predictors.append(MeanReversionPredictor())

        print(f"🧠 Инициализировано {len(self.predictors)} моделей "
              f"для режима {self.mode}")

    # ------------------------------------------------------------- predict ---

    def predict(self, ticker: str, data: pd.DataFrame, days_ahead: int) -> Dict:
        if not self.predictors:
            return self._fallback_prediction(data, days_ahead)

        try:
            individual = []
            for predictor in self.predictors:
                try:
                    pred = predictor.predict(ticker, data, days_ahead)
                    if pred and 'error' not in pred:
                        # калибровка уверенности каждой модели по результатам бэктеста
                        pred['raw_confidence'] = pred.get('confidence', 0.5)
                        pred['confidence'] = self.store.calibrated_confidence(
                            pred.get('confidence', 0.5))
                        individual.append(pred)
                except Exception as e:
                    print(f"Ошибка в модели {predictor.name}: {e}")

            if not individual:
                return self._fallback_prediction(data, days_ahead)

            if len(individual) == 1:
                result = dict(individual[0])
                result['models_used'] = [individual[0].get('model', 'unknown')]
            else:
                result = self._combine(individual, days_ahead, ticker)

            if self.mode == 3:
                result['individual_predictions'] = individual

            return result
        except Exception:
            return self._fallback_prediction(data, days_ahead)

    def _combine(self, preds, horizon: int, ticker: str) -> Dict:
        num_price = den_w = 0.0
        votes_pos = votes_neg = 0.0
        confs, weights, names = [], [], []

        for p in preds:
            w_store = self.store.get_weight(p.get('model', ''), horizon, ticker)
            conf = float(p.get('confidence', 0.5))
            w = max(w_store * conf, 1e-6)
            num_price += float(p['price']) * w
            den_w += w
            chg = float(p.get('change_percent', 0))
            if chg > 0:
                votes_pos += w
            elif chg < 0:
                votes_neg += w
            confs.append(conf)
            weights.append(w_store)
            names.append(p.get('model', 'unknown'))

        final_price = num_price / den_w
        total_votes = votes_pos + votes_neg
        direction_share = max(votes_pos, votes_neg) / total_votes if total_votes else 0.5
        avg_conf = float(np.mean(confs))

        changes = [float(p.get('change_percent', 0)) for p in preds]
        mean_change = float(np.mean(changes))
        spread = float(np.std(changes)) / (abs(mean_change) + 1e-6)
        consistency = float(np.clip(1 / (1 + 0.5 * spread), 0.4, 1.0))

        final_conf = float(np.clip(avg_conf * (0.55 + 0.45 * direction_share) * consistency,
                                   0.25, 0.95))

        # знак итогового изменения приводим к взвешенному голосованию направлений
        change_pct = mean_change
        if votes_neg > votes_pos and change_pct > 0:
            change_pct = -abs(change_pct)
        elif votes_pos > votes_neg and change_pct < 0:
            change_pct = abs(change_pct)

        return {
            'price': round(final_price, 2),
            'change_percent': round(change_pct, 2),
            'confidence': round(final_conf, 3),
            'model': f'{self.name}_{self.mode}',
            'models_used': names,
            'consistency': round(consistency, 3),
            'direction_agreement': round(direction_share, 3),
            'model_weights': {n: round(w, 3) for n, w in zip(names, weights)},
        }
