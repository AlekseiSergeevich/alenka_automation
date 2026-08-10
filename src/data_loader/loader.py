import os
import pandas as pd

def load_sales_data(folder_path):
    """
    Загружает и объединяет данные продаж из всех Excel файлов в папке.

    Args:
        folder_path: Путь к папке с Excel файлами

    Returns:
        pd.DataFrame: Объединённый DataFrame со всеми данными продаж
    """

    file_paths = os.listdir(folder_path)
    all_data = []

    for file in file_paths:
        # Берём только Excel
        if not file.endswith(".xlsx") or file.startswith("~$"):
            continue

        file_path = os.path.join(folder_path, file)

        try:
            # Читаем дату из 3-й строки с явным указанием engine
            date_df = pd.read_excel(file_path, header=None, nrows=3, engine="openpyxl")

            date_range = date_df.iloc[2, 0]

            if pd.isna(date_range):
                continue

            data_range_str = str(date_range).strip()
            if "-" not in data_range_str:
                continue

            month = extract_month_from_date_range(data_range_str)

            # Читаем основную таблицу
            body_data = extract_sales_columns(file_path, month)

            all_data.append(body_data)

        except Exception as e:
            print(f"Ошибка при обработке {file}: {e}")
            continue

    # Склеиваем всё
    return pd.concat(all_data, ignore_index=True)


def extract_month_from_date_range(date_range_str: str) -> pd.Period:
    """
    Извлекает месяц из строки с диапазоном дат.

    Args:
        date_range_str: Строка с диапазоном дат, например "01-01-2024 - 31-01-2024"

    Returns:
        pd.Period: Месяц в формате Period (например, '2024-01')

    Raises:
        ValueError: Если дата в неправильном формате

    Example:
        >>> extract_month_from_date_range("01-01-2024 - 31-01-2024")
        Period('2024-01', 'M')
    """

    start_date = date_range_str.split("-")[0].strip()
    month = pd.to_datetime(start_date, dayfirst=True).to_period("M")
    return month


def extract_sales_columns(file_path, month: pd.Period) -> pd.DataFrame:
    """
    Читает Excel файл и выбирает только нужные столбцы продаж.

    Args:
        file_path: Путь к Excel файлу
        month: Месяц для добавления в новый столбец

    Returns:
        pd.DataFrame: DataFrame с столбцами [Название, Артикул, Кол-во, Ед. изм., month]
    """

    df = pd.read_excel(file_path, skiprows=13, engine="openpyxl")
    df = df.iloc[:, [0, 2, 3, 4]]
    df.columns = ["product", "sku", "qty", "unit"]

    df = df[df["unit"].notna()]
    df = df[df["unit"].astype(str).str.strip() != ""]

    df["month"] = month

    return df


if __name__ == "__main__":
    from pathlib import Path

    data_path = Path("data/raw/2025_sales")
    output_path = Path("data/clean")

    # Создаем папку вывода, если ее нет
    output_path.mkdir(parents=True, exist_ok=True)

    df = load_sales_data(data_path)

    print(df.head())
    print(f"\nЗагружено {len(df)} строк")

    # Сохраняем в CSV
    output_file = output_path / "sales_data.csv"
    df.to_csv(output_file, index=False, encoding="utf-8")

    print(f"Файл сохранён: {output_file}")
