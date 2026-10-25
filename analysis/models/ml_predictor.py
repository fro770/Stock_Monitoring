"""
ML-предиктор: обучение на истории тикера (walk-forward внутри одного train-сплита),
прогноз доходности за days_ahead + калиброванная уверенность.

Модель обучается ТОЛЬКО на данных до последней даты; цель — доходность через
days_ahead торговых дней. Уверенность корректируется по исторической hit-rate
направления, вычисленной на in-sample walk-forward прогоне (без использования будущего).
"""

import numpy as np
import pandas as pd
from typing import Dict

from .base_predictor import BasePredictor
from .features import build_features, FEATURE_COLUMNS
from .ml_models import MLModelSet, SKLEARN_AVAILABLE


class MLPredictor(BasePredictor):
    """Предсказатель на классических ML-моделях (ансамбль sklearn/xgb/lgbm)."""

    def __init__(self, horizon: int = None):
        super().__init__("ml_ensemble")
        self.horizon = horizon  # если задан — фиксированный горизонт, иначе = days_ahead
        self.min_train_rows = 120

    # ------------------------------------------------------------------ API ---

    def predict(self, ticker: str, data: pd.DataFrame, days_ahead: int) -> Dict:
        try:
            if not SKLEARN_AVAILABLE or data is None or len(data) < self.min_train_rows:
                return self._fallback_prediction(data, days_ahead)

            horizon = self.horizon or days_ahead
            feats = build_features(data)
            close = feats['close_price'].values
            # цель: доходность через horizon баров
            target = np.full(len(close), np.nan)
            target[:-horizon] = close[horizon:] / close[:-horizon] - 1
            X = feats[FEATURE_COLUMNS].values.astype(float)
            valid = ~np.isnan(target) & ~np.isnan(X).any(axis=1)
            Xv, yv = X[valid], target[valid]
            if len(yv) < self.min_train_rows:
                return self._fallback_prediction(data, days_ahead)

            # сплит: последние 20% — «валидация» для оценки hit-rate
            split = max(int(len(yv) * 0.8), len(yv) - 60)
            ms = MLModelSet()
            info = ms.fit_predict_info(Xv[:split], yv[:split], Xv[-1:])
            if not info['models']:
                return self._fallback_prediction(data, days_ahead)

            # оценка качества на holdout (walk-forward упрощённый: один retrain)
            hit_rate, mae_rel = self._holdout_quality(Xv, yv, split, horizon)

            pred_ret = float(np.clip(info['return'], -0.30, 0.30))
            last_price = float(data['close_price'].iloc[-1])
            predicted_price = last_price * (1 + pred_ret)

            # уверенность: согласованность моделей × историческая hit-rate
            base_conf = info['confidence']
            calibrated = 0.5 * base_conf + 0.5 * hit_rate
            confidence = float(np.clip(calibrated, 0.30, 0.95))

            return {
                'price': round(predicted_price, 2),
                'change_percent': round(pred_ret * 100, 2),
                'confidence': round(confidence, 3),
                'model': self.name,
                'models_used': info['models'],
                'hit_rate': round(hit_rate, 3),
                'mae_rel': round(mae_rel, 4),
                'agreement': info['agreement'],
            }
        except Exception:
            return self._fallback_prediction(data, days_ahead)

    # ------------------------------------------------------------- helpers ---

    def _holdout_quality(self, X: np.ndarray, y: np.ndarray, split: int,
                         horizon: int) -> tuple:
        """Hit-rate направления и относительная MAE на holdout с одним переобучением."""
        try:
            ms = MLModelSet()
            info = ms.fit_predict_info(X[:split], y[:split], X[split:])
            pred = np.full(len(y) - split, info['return'])
            actual = y[split:]
            hit = float(np.mean(np.sign(pred) == np.sign(actual))) if len(actual) else 0.5
            mae = float(np.mean(np.abs(pred - actual)))
            denom = float(np.mean(np.abs(actual)) + 1e-9)
            mae_rel = mae / denom
            return hit, mae_rel
        except Exception:
            return 0.5, 1.0
