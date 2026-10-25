"""
Статистические предикторы (новые модели в ансамбле):

1. ARSMPredictor — авторегрессия AR(p) по логарифмическим доходностям + GARCH(1,1)-подобная
   оценка волатильности для интервального прогноза и уверенности. Реализован без
   statsmodels (чистый numpy: Yule-Walker / МНК), устойчив к выбросам.

2. MeanReversionPredictor — модель возврата к среднему: z-score цены относительно
   EMA-канала, half-life по ACF, прогноз с экспоненциальным возвратом; уверенность
   снижается при сильном тренде (ADX), т.к. mean reversion тогда не работает.

Оба возвращают стандартный dict: price / change_percent / confidence / model.
"""

import numpy as np
import pandas as pd
from typing import Dict

from .base_predictor import BasePredictor


# --------------------------------------------------------------------- AR ---

def _fit_ar(y: np.ndarray, p: int = 5) -> tuple:
    """МНК-оценка AR(p). Возвращает (phi, sigma_resid)."""
    y = np.asarray(y, dtype=float)
    y = y[~np.isnan(y)]
    if len(y) < 4 * p:
        return None, None
    Y = y[p:]
    X = np.column_stack([y[p - k - 1:len(y) - k - 1] for k in range(p)] + [np.ones(len(Y))])
    try:
        phi, *_ = np.linalg.lstsq(X, Y, rcond=None)
        resid = Y - X @ phi
        sigma = float(np.std(resid))
        # стабилизация: обрезаем коэффициенты, чтобы процесс был стационарным
        phi = np.clip(phi, -0.98, 0.98)
        return phi[:-1], sigma
    except Exception:
        return None, None


def _garch11_sigma(resid: np.ndarray, omega=None, alpha=0.08, beta=0.90) -> float:
    """Оценка условной волатильности GARCH(1,1) (итеративно, финальное σ)."""
    r2 = np.asarray(resid, dtype=float) ** 2
    if len(r2) < 20:
        return float(np.std(r2) ** 0.5 + 1e-9)
    if omega is None:
        omega = float(np.mean(r2)) * 0.05
    sig2 = float(np.mean(r2[-30:]))
    for x in r2:
        sig2 = omega + alpha * x + beta * sig2
    return float(np.sqrt(max(sig2, 1e-12)))


class ARSMPredictor(BasePredictor):
    """AR(p)+GARCH: прогноз накопленной лог-доходности на горизонт."""

    def __init__(self, order: int = 5):
        super().__init__("ar_garch")
        self.order = order

    def predict(self, ticker: str, data: pd.DataFrame, days_ahead: int) -> Dict:
        try:
            if data is None or len(data) < 60 or 'close_price' not in data:
                return self._fallback_prediction(data, days_ahead)
            close = data['close_price'].astype(float).values
            logret = np.diff(np.log(close))
            phi, sigma = _fit_ar(logret, self.order)
            if phi is None:
                return self._fallback_prediction(data, days_ahead)

            # прогноз h шагов вперёд через companion-рекурсию AR
            hist = logret[-self.order:]
            forecast_steps = []
            cur = hist.copy()
            for _ in range(min(days_ahead, 60)):
                nxt = float(np.dot(phi, cur[::-1][:len(phi)]))
                forecast_steps.append(nxt)
                cur = np.append(cur[1:], nxt)
            cum_logret = float(np.sum(forecast_steps))
            # сжатие к нулю: долгий горизонт AR-прогноз ненадёжен
            shrink = 1.0 / (1.0 + 0.05 * days_ahead)
            cum_logret *= shrink

            garch_sigma = _garch11_sigma(logret[-120:])
            horizon_vol = garch_sigma * np.sqrt(days_ahead)
            rel_unc = abs(cum_logret) / (horizon_vol + 1e-9)
            confidence = float(np.clip(0.45 + 0.35 * min(rel_unc, 1.5) / 1.5, 0.3, 0.85))

            last = float(close[-1])
            pred_price = last * np.exp(cum_logret)
            return {
                'price': round(pred_price, 2),
                'change_percent': round((pred_price / last - 1) * 100, 2),
                'confidence': round(confidence, 3),
                'model': self.name,
                'interval_95': [round(float(pred_price * np.exp(-1.96 * horizon_vol)), 2),
                               round(float(pred_price * np.exp(1.96 * horizon_vol)), 2)],
                'sigma_daily': round(garch_sigma, 5),
            }
        except Exception:
            return self._fallback_prediction(data, days_ahead)


# ---------------------------------------------------------- Mean reversion ---

class MeanReversionPredictor(BasePredictor):
    """Возврат к среднему по z-score в EMA-канале с учётом half-life."""

    def __init__(self, window: int = 30):
        super().__init__("mean_reversion")
        self.window = window

    def predict(self, ticker: str, data: pd.DataFrame, days_ahead: int) -> Dict:
        try:
            if data is None or len(data) < 60 or 'close_price' not in data:
                return self._fallback_prediction(data, days_ahead)
            s = data['close_price'].astype(float)
            ema_fast = s.ewm(span=self.window, adjust=False).mean()
            dev = (s - ema_fast) / (s.rolling(self.window, min_periods=10).std().replace(0, np.nan))
            z = float(dev.iloc[-1])
            if np.isnan(z):
                return self._fallback_prediction(data, days_ahead)

            # half-life из ACF дневных изменений z (упрощённо: AR(1) на z)
            zv = dev.dropna().values
            rho = float(np.corrcoef(zv[:-1], zv[1:])[0, 1]) if len(zv) > 30 else 0.7
            rho = np.clip(rho, 0.01, 0.99)
            half_life = np.log(0.5) / np.log(rho) if rho < 1 else 30

            # ожидаемая доля «выравнивания» за горизонт
            decay = 1 - rho ** days_ahead
            expected_move = -z * decay * float(s.rolling(self.window, min_periods=10).std().iloc[-1]) / float(s.iloc[-1])
            expected_move = float(np.clip(expected_move, -0.20, 0.20))

            # уверенность: тем выше, чем сильнее отклонение и слабее тренд
            adx_like = abs(float(np.polyfit(np.arange(min(20, len(s))), s.values[-min(20, len(s)):], 1)[0])) \
                / float(s.iloc[-1])
            trend_penalty = float(np.clip(1 - 200 * adx_like, 0.5, 1.0))
            strength = float(np.clip(abs(z) / 2.5, 0, 1))
            confidence = float(np.clip(0.35 + 0.45 * strength * trend_penalty, 0.3, 0.85))

            last = float(s.iloc[-1])
            pred = last * (1 + expected_move)
            return {
                'price': round(pred, 2),
                'change_percent': round(expected_move * 100, 2),
                'confidence': round(confidence, 3),
                'model': self.name,
                'z_score': round(z, 3),
                'half_life_days': round(float(half_life), 1),
            }
        except Exception:
            return self._fallback_prediction(data, days_ahead)
