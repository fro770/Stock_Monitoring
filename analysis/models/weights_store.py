"""
Хранилище весов моделей (самообучаемый ансамбль).

Файл data/model_weights.json:
{
  "version": 2,
  "updated": "...",
  "global_weights": {"trend": 1.0, "finrl": 1.0, "ml_ensemble": 1.4, ...},
  "horizon_weights": {7: {"trend": 1.2, ...}},          # веса по горизонтам
  "per_ticker_weights": {"SBER": {...}},                # опционально
  "calibration": {"slope": 1.0, "intercept": 0.0},      # калибровка уверенности
  "history": [ {...} ]                                   # последние прогоны бэктеста
}

Веса обновляет BacktestCalibrator (analysis/core/backtest.py) после самопроверки.
"""

import json
import os
from datetime import datetime
from typing import Dict

from ..core.config import Config

WEIGHTS_FILE = os.path.join(Config.DATA_DIR, "model_weights.json")

DEFAULT_GLOBAL_WEIGHTS = {
    'trend': 1.0,
    'finrl': 1.0,
    'finrl_enhanced': 1.0,
    'ml_ensemble': 1.3,
    'ar_garch': 1.1,
    'mean_reversion': 0.9,
    'fallback': 0.5,
}


class WeightStore:
    """Потокобезопасное чтение/запись весов моделей."""

    _lock_file = WEIGHTS_FILE + ".lock"

    def __init__(self, path: str = WEIGHTS_FILE):
        self.path = path
        self.data = self._load()

    def _load(self) -> Dict:
        try:
            if os.path.exists(self.path):
                with open(self.path, 'r', encoding='utf-8') as f:
                    d = json.load(f)
                if isinstance(d, dict) and 'global_weights' in d:
                    return d
        except Exception:
            pass
        return {
            'version': 2,
            'updated': None,
            'global_weights': dict(DEFAULT_GLOBAL_WEIGHTS),
            'horizon_weights': {},
            'per_ticker_weights': {},
            'calibration': {'slope': 1.0, 'intercept': 0.0},
            'history': [],
        }

    def save(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        self.data['updated'] = datetime.now().isoformat()
        tmp = self.path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)

    # ------------------------------------------------------------- getters ---

    def get_weight(self, model_name: str, horizon: int = None,
                   ticker: str = None) -> float:
        """Приоритет: per_ticker > horizon > global > default."""
        w = DEFAULT_GLOBAL_WEIGHTS.get(model_name, 1.0)
        g = self.data.get('global_weights', {})
        if model_name in g:
            w = float(g[model_name])
        if horizon is not None:
            hw = self.data.get('horizon_weights', {}).get(str(horizon)) or \
                 self.data.get('horizon_weights', {}).get(horizon) or {}
            if model_name in hw:
                w = float(hw[model_name])
        if ticker is not None:
            tw = self.data.get('per_ticker_weights', {}).get(ticker) or {}
            if model_name in tw:
                w = float(tw[model_name])
        return max(0.0, min(w, 5.0))

    def get_calibration(self) -> Dict:
        c = self.data.get('calibration', {})
        return {'slope': float(c.get('slope', 1.0)),
                'intercept': float(c.get('intercept', 0.0))}

    def calibrated_confidence(self, raw_conf: float) -> float:
        """Линейная калибровка уверенности по результатам бэктеста."""
        c = self.get_calibration()
        val = c['slope'] * float(raw_conf) + c['intercept']
        return round(float(np.clip(val, 0.05, 0.99)), 3) if _np_available else \
            round(max(0.05, min(0.99, val)), 3)

    # ------------------------------------------------------------- setters ---

    def set_global_weights(self, weights: Dict[str, float]):
        self.data.setdefault('global_weights', {}).update(
            {k: round(float(v), 4) for k, v in weights.items()})

    def set_horizon_weights(self, horizon: int, weights: Dict[str, float]):
        self.data.setdefault('horizon_weights', {})[str(horizon)] = \
            {k: round(float(v), 4) for k, v in weights.items()}

    def set_calibration(self, slope: float, intercept: float):
        self.data['calibration'] = {'slope': round(float(slope), 4),
                                    'intercept': round(float(intercept), 4)}

    def append_history(self, record: Dict, keep: int = 20):
        h = self.data.setdefault('history', [])
        h.append(record)
        self.data['history'] = h[-keep:]


try:
    import numpy as np
    _np_available = True
except Exception:
    _np_available = False
