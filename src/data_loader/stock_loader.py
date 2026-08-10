import os
import pandas as pd


def load_stocks_data(file_path: str) -> pd.DataFrame:
    """
    Загружает данные по остаткам из одного Excel файла.

    Args:
        file_path: Путь к Excel файлу

    Returns:
        pd.DataFrame: DataFrame с данными остатков
    """
    try:
        # Читаем дату из 3-й строки
        date_df = pd.read_excel(file_path, header=None, nrows=3, engine="openpyxl")

        curr_date = date_df.iloc[2, 0]

        if pd.isna(curr_date):
            raise ValueError("Дата не найдена в файле")

        curr_date_str = str(curr_date).strip()

        month = pd.to_datetime(curr_date_str, dayfirst=True).to_period("M")

        # Читаем основную таблицу
        body_data = extract_stocks_columns(file_path, month)

        print(f"✅ Данные загружены успешно из {file_path}")
        return body_data

    except Exception as e:
        print(f"❌ Ошибка при обработке {file_path}: {e}")
        raise


def extract_stocks_columns(file_path: str, month: pd.Period) -> pd.DataFrame:
    """
    Извлекает нужные столбцы из файла с данными по остаткам.

    Args:
        file_path: Путь к файлу
        month: Месяц, к которому относятся данные

    Returns:
        pd.DataFrame: DataFrame с нужными столбцами и добавленным месяцем
    """

    df = pd.read_excel(file_path, skiprows=14, engine="openpyxl")
    df = df.iloc[:, [0, 1, 3, 4]]
    df.columns = ["product", "sku", "qty", "unit"]

    # Фильтруем строки с пустыми значениями в столбце "unit"
    df = df[df["unit"].notna()]
    df = df[df["unit"].astype(str).str.strip() != ""]

    df["month"] = month

    return df


if __name__ == "__main__":
    from pathlib import Path
    from datetime import datetime

    # Путь к файлу со своими данными
    file_path = "data/raw/stocks/stocks.xlsx"
    output_path = Path("data/clean")

    # Загружаем данные из одного файла
    df = load_stocks_data(file_path)

    print(df.head())
    print(f"\n✅ Загружено {len(df)} строк")
    print(f"Дата обработки: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}")

    # Создаём папку вывода, если её нет
    output_path.mkdir(parents=True, exist_ok=True)

    # Сохраняем в CSV
    output_file = output_path / "current_stocks_data.csv"
    df.to_csv(output_file, index=False, encoding="utf-8")

    print(f"Файл сохранён: {output_file}")
