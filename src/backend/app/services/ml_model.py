import xgboost as xgb
from pathlib import Path

# Указываем путь к вашей обученной модели (внутри контейнера она смонтирована в /app/src/analytics/models/)
MODEL_PATH = Path("/app/src/analytics/models/xgboost_tweedie_model.json")                 

class ForecastModel:
    def __init__(self):
        self.model = xgb.Booster()
        self.is_loaded = False

    def load(self):
        if not self.is_loaded:
            self.model.load_model(MODEL_PATH)
            self.is_loaded = True

    def predict(self, features_df):
        """Принимает датафрейм с готовыми фичами и возвращает прогноз"""
        self.load()
        dmatrix = xgb.DMatrix(features_df, enable_categorical=True)
        # Возвращаем предсказания, отбрасывая отрицательные значения (продажи >= 0)
        preds = self.model.predict(dmatrix)
        return [max(0, float(p)) for p in preds]

# Создаем глобальный экземпляр (Singleton), чтобы загрузить его в память 1 раз
forecast_model = ForecastModel()