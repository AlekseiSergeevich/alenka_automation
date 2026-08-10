from pathlib import Path
import pandas as pd


def get_unique_skus(sales_df: pd.DataFrame, stocks_df: pd.DataFrame) -> pd.DataFrame:

    missing_in_sale = (
        sales_df[["sku", "product"]]
        .drop_duplicates()
        .merge(stocks_df[["sku", "product", "qty", "unit"]], on="sku", how="right", indicator=True)
    )
    missing_in_sale = missing_in_sale[missing_in_sale["_merge"] == "right_only"]

    return missing_in_sale


def main():
    try:

        output_path = Path("data/clean")
        sales_data_path = output_path / "sales_data.csv"
        stocks_data_path = output_path / "current_stocks_data.csv"
        sales_data = pd.read_csv(sales_data_path)
        stocks_data = pd.read_csv(stocks_data_path)

        missing_skus = get_unique_skus(sales_data, stocks_data)
        output_file = output_path / "missing_in_sales_sku.csv"

        # Создаём папку вывода на всякий случай
        output_path.mkdir(parents=True, exist_ok=True)

        missing_skus.to_csv(output_file, index=False)
        print("Создан файл с уникальными SKU, отсутствующими в продажах.")

    except Exception as e:
        print(f"Ошибка при создании файла с уникальными SKU: {e}")


if __name__ == "__main__":
    main()
