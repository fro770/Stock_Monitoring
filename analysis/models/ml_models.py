"""
ML-модели прогноза: регрессия (цена/доходность) и классификация (рост/падение).

Используют единый набор признаков из analysis.models.features.
Каждая модель умеет:
 - fit(X, y)  — обучение на исторических признаках,
 - predict(X) — прогноз доходности за горизонт (в долях),
 - direction_probability(X) — вероятность роста (для оценки уверенности).

Ансамбль MLModelSet объединяет Ridge/Lasso/ElasticNet/RandomForest/GBM/SVR
(при доступности XGBoost/LightGBM — они добавляются автоматически).
"""

import warnings

import numpy as np

warnings.filterwarnings("ignore", category=FutureWarning)

try:
    from sklearn.linear_model import Ridge, Lasso, ElasticNet
    from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
    from sklearn.svm import SVR
    from sklearn.preprocessing import StandardScaler
    from sklearn.impute import SimpleImputer
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False

try:
    from xgboost import XGBRegressor
    XGB_AVAILABLE = True
except Exception:
    XGB_AVAILABLE = False

try:
    from lightgbm import LGBMRegressor
    LGBM_AVAILABLE = True
except Exception:
    LGBM_AVAILABLE = False


def _clean_matrix(X: np.ndarray) -> np.ndarray:
    """Замена NaN/Inf на 0 (нейтральные значения признаков)."""
    X = np.nan_to_num(np.asarray(X, dtype=float), nan=0.0, posinf=0.0, neginf=0.0)
    return X


class MLModel:
    """Обёртка над одной sklearn-моделью (регрессор доходности)."""

    def __init__(self, name: str, estimator, scale: bool = False):
        self.name = name
        self.estimator = estimator
        self.scale = scale
        self._scaler = None
        self.trained = False
        self._train_std = 1.0

    def fit(self, X: np.ndarray, y: np.ndarray):
        if not SKLEARN_AVAILABLE:
            return self
        X = _clean_matrix(X)
        y = np.asarray(y, dtype=float)
        if len(y) < 10 or np.allclose(y, 0):
            return self
        try:
            if self.scale:
                self._scaler = StandardScaler()
                Xs = self._scaler.fit_transform(X)
                ys = (y - y.mean()) / (y.std() + 1e-9)
                self._train_std = float(y.std() + 1e-9)
                self.estimator.fit(Xs, ys)
            else:
                # клиппинг экстремальных целей (выбросы котировок)
                lo, hi = np.percentile(y, [1, 99])
                yc = np.clip(y, lo, hi)
                self._train_std = float(np.std(yc) + 1e-9)
                self.estimator.fit(X, yc)
            self.trained = True
        except Exception:
            self.trained = False
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        """Прогноз доходности (в долях) для каждой строки признаков."""
        if not self.trained:
            return np.zeros(len(X))
        X = _clean_matrix(X)
        try:
            if self.scale and self._scaler is not None:
                pred = self.estimator.predict(self._scaler.transform(X)) * self._train_std
            else:
                pred = self.estimator.predict(X)
            # разумное ограничение: не более ±25% за горизонт
            return np.clip(pred, -0.25, 0.25)
        except Exception:
            return np.zeros(len(X))

    def feature_importance(self) -> dict:
        """Важность признаков (если доступна)."""
        try:
            est = getattr(self.estimator, 'steps', [(None, self.estimator)])[-1][1] \
                if hasattr(self.estimator, 'steps') else self.estimator
            imp = getattr(est, 'feature_importances_', None)
            if imp is None and hasattr(est, 'coef_'):
                imp = np.abs(np.ravel(est.coef_))
            if imp is None:
                return {}
            return {str(i): float(v) for i, v in enumerate(imp)}
        except Exception:
            return {}


def make_default_models():
    """Список базовых моделей ансамбля (настраивается при импорте sklearn)."""
    if not SKLEARN_AVAILABLE:
        return []
    models = [
        MLModel('ridge', Ridge(alpha=1.0)),
        MLModel('elasticnet', ElasticNet(alpha=0.001, l1_ratio=0.5)),
        MLModel('rf', RandomForestRegressor(
            n_estimators=120, max_depth=6, min_samples_leaf=8,
            random_state=42, n_jobs=-1)),
        MLModel('gbm', GradientBoostingRegressor(
            n_estimators=150, max_depth=3, learning_rate=0.05,
            subsample=0.9, random_state=42)),
        MLModel('svr', SVR(C=1.0, epsilon=0.05), scale=True),
    ]
    if XGB_AVAILABLE:
        models.append(MLModel('xgb', XGBRegressor(
            n_estimators=200, max_depth=4, learning_rate=0.05,
            subsample=0.9, colsample_bytree=0.8, random_state=42,
            verbosity=0)))
    if LGBM_AVAILABLE:
        models.append(MLModel('lgbm', LGBMRegressor(
            n_estimators=200, max_depth=5, learning_rate=0.05,
            subsample=0.9, colsample_bytree=0.8, random_state=42,
            verbose=-1)))
    return models


class MLModelSet:
    """Ансамбль ML-моделей с согласованной оценкой уверенности.

    Уверенность = base_confidence * agreement_factor * quality_factor, где:
      - agreement_factor — доля моделей, предсказавших то же направление;
      - quality_factor — сжатие к 0.5 при большом разбросе прогнозов (disagreement).
    Это снижает «самоуверенность» при противоречиях моделей и повышает её
    при их согласии — корректная калибровка важнее сырой точности.
    """

    def __init__(self, models=None):
        self.models = models if models is not None else make_default_models()

    @property
    def available(self) -> bool:
        return SKLEARN_AVAILABLE and len(self.models) > 0

    def fit_predict_info(self, X_train: np.ndarray, y_train: np.ndarray,
                         X_pred: np.ndarray) -> dict:
        """Обучает все модели и делает усреднённый прогноз по X_pred."""
        preds, names = [], []
        for m in self.models:
            mm = MLModel(m.name, type(m.estimator)(**m.estimator.get_params())
                         if SKLEARN_AVAILABLE else None, scale=m.scale)
            mm.fit(X_train, y_train)
            if mm.trained:
                preds.append(mm.predict(X_pred))
                names.append(mm.name)
        if not preds:
            return {'return': 0.0, 'confidence': 0.3, 'models': []}
        P = np.vstack(preds)
        mean_ret = float(np.mean(P[0]))
        signs = np.sign(P)
        agree = float(np.mean(signs == np.sign(mean_ret))) if mean_ret != 0 else 0.5
        spread = float(np.std(P[0]) / (abs(mean_ret) + 1e-6))
        quality = float(np.clip(1 / (1 + spread), 0.4, 1.0))
        confidence = float(np.clip(0.55 * agree + 0.35 * quality + 0.10, 0.3, 0.95))
        return {
            'return': mean_ret,
            'confidence': round(confidence, 3),
            'models': names,
            'per_model_return': round(float(mean_ret), 5),
            'agreement': round(agree, 3),
        }
