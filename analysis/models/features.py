"""
Генерация признаков (feature engineering) для ML-моделей прогноза.

Единый источник признаков для всех моделей и бэктестера:
 - лаги доходности, скользящие средние и их отношения,
 - технические индикаторы (RSI, MACD, Stochastic, BBands, ATR, ADX, CCI, Williams %R),
 - волатильность, моментум, объёмные признаки (OBV-норм, VWAP-отклонение).

Все признаки рассчитываются ТОЛЬКО по данным до даты включительно
(без заглядывания в будущее) — безопасно для walk-forward тестирования.
"""

import numpy as np
import pandas as pd

PRICE_COL = 'close_price'


# ---------------------------------------------------------------- базовые ---

def _returns(close: pd.Series) -> pd.Series:
    return close.pct_change()


def sma(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window, min_periods=max(3, window // 2)).mean()


def ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    out = 100 - 100 / (1 + rs)
    return out.fillna(50.0)


def macd(close: pd.Series, fast=12, slow=26, signal=9):
    macd_line = ema(close, fast) - ema(close, slow)
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    hist = macd_line - signal_line
    return macd_line, signal_line, hist


def stochastic(df: pd.DataFrame, k_period=14, d_period=3):
    low_min = df['low'].rolling(k_period, min_periods=5).min() if 'low' in df else None
    high_max = df['high'].rolling(k_period, min_periods=5).max() if 'high' in df else None
    close = df[PRICE_COL]
    if low_min is None or high_max is None:
        # фолбэк: используем сам close как диапазон
        low_min, high_max = close.rolling(k_period).min(), close.rolling(k_period).max()
    k = 100 * (close - low_min) / (high_max - low_min).replace(0, np.nan)
    d = k.rolling(d_period).mean()
    return k.fillna(50), d.fillna(50)


def bollinger_position(close: pd.Series, window=20, num_std=2.0) -> pd.Series:
    """Позиция цены внутри полос Боллинджера: -1 (у нижней) .. +1 (у верхней)."""
    mid = sma(close, window)
    std = close.rolling(window, min_periods=5).std()
    width = (2 * num_std * std).replace(0, np.nan)
    return ((close - mid) / width).clip(-2, 2).fillna(0)


def atr(df: pd.DataFrame, period=14) -> pd.Series:
    if not all(c in df.columns for c in ('high', 'low')):
        tr = df[PRICE_COL].diff().abs()
    else:
        h, l, c = df['high'], df['low'], df[PRICE_COL].shift()
        tr = pd.concat([h - l, (h - c).abs(), (l - c).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False).mean()


def adx(df: pd.DataFrame, period=14) -> pd.Series:
    if not all(c in df.columns for c in ('high', 'low')):
        # без OHLC упрощённый аналог: сила тренда по |изменению SMA|/ATR-подобному разбросу
        up = df[PRICE_COL].diff().clip(lower=0)
        dn = (-df[PRICE_COL].diff()).clip(lower=0)
        tr = df[PRICE_COL].diff().abs().rolling(period).sum()
    else:
        h, l = df['high'], df['low']
        up = h.diff()
        dn = -l.diff()
        plus_dm = np.where((up > dn) & (up > 0), up, 0.0)
        minus_dm = np.where((dn > up) & (dn > 0), dn, 0.0)
        tr = pd.concat([(h - l),
                        (h - df[PRICE_COL].shift()).abs(),
                        (l - df[PRICE_COL].shift()).abs()], axis=1).max(axis=1)
        up, dn = plus_dm, minus_dm
    atr_ = tr.ewm(alpha=1 / period, adjust=False).mean().replace(0, np.nan)
    plus_di = 100 * pd.Series(up, index=df.index).ewm(alpha=1 / period, adjust=False).mean() / atr_
    minus_di = 100 * pd.Series(dn, index=df.index).ewm(alpha=1 / period, adjust=False).mean() / atr_
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    return dx.ewm(alpha=1 / period, adjust=False).mean().fillna(20)


def cci(df: pd.DataFrame, period=20) -> pd.Series:
    tp = (df['high'] + df['low'] + df[PRICE_COL]) / 3 if all(c in df for c in ('high', 'low')) else df[PRICE_COL]
    ma = sma(tp, period)
    md = (tp - ma).abs().rolling(period, min_periods=5).mean()
    return ((tp - ma) / (0.015 * md.replace(0, np.nan))).clip(-300, 300).fillna(0)


def willr(df: pd.DataFrame, period=14) -> pd.Series:
    close = df[PRICE_COL]
    if all(c in df for c in ('high', 'low')):
        hh, ll = df['high'].rolling(period, min_periods=5).max(), df['low'].rolling(period, min_periods=5).min()
    else:
        hh, ll = close.rolling(period).max(), close.rolling(period).min()
    return (-100 * (hh - close) / (hh - ll).replace(0, np.nan)).fillna(-50)


def obv_norm(df: pd.DataFrame, window=20) -> pd.Series:
    """Нормализованный OBV: z-score объёма со знаком цены за окно."""
    close = df[PRICE_COL]
    vol = df['volume'] if 'volume' in df else pd.Series(1.0, index=df.index)
    direction = np.sign(close.diff()).fillna(0)
    obv = (direction * vol).cumsum()
    chg = obv.diff(window)
    z = (chg - chg.rolling(window * 3, min_periods=window).mean()) / \
        chg.rolling(window * 3, min_periods=window).std().replace(0, np.nan)
    return z.clip(-3, 3).fillna(0)


def vwap_deviation(df: pd.DataFrame, window=20) -> pd.Series:
    """Отклонение цены от «скользящего VWAP» за окно (в единицах σ цены)."""
    close = df[PRICE_COL]
    if 'volume' in df and 'high' in df and 'low' in df:
        tp = (df['high'] + df['low'] + close) / 3
        vol = df['volume'].astype(float)
        num = (tp * vol).rolling(window, min_periods=5).sum()
        den = vol.rolling(window, min_periods=5).sum().replace(0, np.nan)
        vwap = num / den
    else:
        vwap = sma(close, window)
    std = close.rolling(window, min_periods=5).std().replace(0, np.nan)
    return ((close - vwap) / std).clip(-3, 3).fillna(0)


# ------------------------------------------------------------------ main ---

FEATURE_COLUMNS = [
    'ret_1', 'ret_2', 'ret_3', 'ret_5', 'ret_10', 'ret_20',
    'sma_ratio_5_20', 'sma_ratio_10_30', 'sma_ratio_20_50',
    'price_vs_sma20', 'price_vs_sma50',
    'rsi_14', 'rsi_7', 'macd_hist_norm', 'stoch_k', 'stoch_d',
    'bb_pos', 'atr_pct', 'adx_14', 'cci_20', 'willr_14',
    'volatility_10', 'volatility_30', 'mom_slope_10', 'mom_slope_30',
    'obv_z', 'vwap_dev', 'day_of_week_sin', 'day_of_week_cos',
]


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """Строит таблицу признаков по DataFrame с колонками Date/close_price (+OHLCV опц.)."""
    if PRICE_COL not in df.columns:
        raise ValueError(f"Нет колонки {PRICE_COL}")
    d = df.reset_index(drop=True).copy()
    if 'Date' in d.columns:
        d = d.sort_values('Date').reset_index(drop=True)
    close = d[PRICE_COL].astype(float)
    ret = _returns(close)

    f = pd.DataFrame(index=d.index)
    # лаги доходностей
    for lag, name in [(1, 'ret_1'), (2, 'ret_2'), (3, 'ret_3'), (5, 'ret_5'), (10, 'ret_10'), (20, 'ret_20')]:
        f[name] = ret.shift(lag)
    # отношения средних
    s5, s10, s20, s30, s50 = (sma(close, w) for w in (5, 10, 20, 30, 50))
    f['sma_ratio_5_20'] = s5 / s20 - 1
    f['sma_ratio_10_30'] = s10 / s30 - 1
    f['sma_ratio_20_50'] = s20 / s50 - 1
    f['price_vs_sma20'] = close / s20 - 1
    f['price_vs_sma50'] = close / s50 - 1
    # индикаторы
    f['rsi_14'] = rsi(close, 14) / 100
    f['rsi_7'] = rsi(close, 7) / 100
    _, _, hist = macd(close)
    f['macd_hist_norm'] = (hist / close).clip(-0.1, 0.1) * 100
    k, dd = stochastic(d)
    f['stoch_k'] = k / 100
    f['stoch_d'] = dd / 100
    f['bb_pos'] = bollinger_position(close)
    atr_v = atr(d)
    f['atr_pct'] = (atr_v / close).clip(0, 0.2) * 100
    f['adx_14'] = adx(d) / 100
    f['cci_20'] = cci(d) / 300
    f['willr_14'] = willr(d) / 100
    f['volatility_10'] = ret.rolling(10, min_periods=5).std()
    f['volatility_30'] = ret.rolling(30, min_periods=10).std()
    # наклоны тренда (нормированные к цене)
    def slope(series: pd.Series, window: int) -> pd.Series:
        x = np.arange(window)
        xm = x.mean()
        denom = ((x - xm) ** 2).sum()
        roll_mean = series.rolling(window).mean()
        # регрессионный наклон через свёртку
        b = sum((xi - xm) * series.shift(window - 1 - i) for i, xi in enumerate(x)) / denom
        return b / series.rolling(window).mean()
    f['mom_slope_10'] = slope(ret.cumsum(), 10)
    f['mom_slope_30'] = slope(ret.cumsum(), 30)
    # объём
    f['obv_z'] = obv_norm(d)
    f['vwap_dev'] = vwap_deviation(d)
    # сезонность дня недели
    if 'Date' in d.columns:
        dow = pd.to_datetime(d['Date']).dt.dayofweek
    else:
        dow = pd.Series(np.arange(len(d)) % 5, index=d.index)
    f['day_of_week_sin'] = np.sin(2 * np.pi * dow / 5)
    f['day_of_week_cos'] = np.cos(2 * np.pi * dow / 5)

    f = f[FEATURE_COLUMNS]
    # дата и цена рядом с признаками (для удобства бэктестера)
    f.insert(0, 'Date', d['Date'] if 'Date' in d.columns else pd.to_datetime(pd.Series(range(len(d)))))
    f.insert(1, PRICE_COL, close.values)
    return f
