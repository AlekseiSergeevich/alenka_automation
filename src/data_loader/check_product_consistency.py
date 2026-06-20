"""
Скрипт для проверки консистентности названий товаров по артикулам.

Проверяет, что для каждого уникального артикула все записи имеют одно и то же название.
Если найдены несовпадения, они выводятся в консоль и сохраняются в отдельный CSV файл.
"""

import pandas as pd
from pathlib import Path


def check_product_consistency(csv_path: str) -> dict:
    """
    Проверяет консистентность названий товаров по артикулам.

    Args:
        csv_path: Путь к файлу sales_data.csv

    Returns:
        dict: Словарь с результатами проверки:
            - total_skus: Количество уникальных артикулов
            - inconsistent_count: Количество артикулов с несовпадениями
            - inconsistent_data: DataFrame с несовпадениями
    """

    # Загружаем данные
    sales_data = pd.read_csv(csv_path)

    print(f"📊 Загружено {len(sales_data)} строк данных")
    print(f"📌 Уникальных артикулов: {sales_data['sku'].nunique()}\n")

    # Группируем по SKU и проверяем названия
    inconsistencies = []

    for sku, group in sales_data.groupby("sku"):
        unique_products = group["product"].unique()

        # Если для артикула больше одного названия товара
        if len(unique_products) > 1:
            inconsistencies.append(
                {
                    "sku": sku,
                    "product_names": " | ".join(unique_products),
                    "count_variants": len(unique_products),
                    "records_count": len(group),
                }
            )

    # Результаты
    total_skus = sales_data["sku"].nunique()
    inconsistent_count = len(inconsistencies)

    print("=" * 80)
    if inconsistent_count == 0:
        print("✅ ОТЛИЧНО! Все артикулы имеют консистентные названия товаров.")
    else:
        print(
            f"❌ НАЙДЕНО НЕСОВПАДЕНИЙ: {inconsistent_count} артикулов имеют разные названия"
        )
        print("=" * 80)

        inconsistencies_df = pd.DataFrame(inconsistencies)

        print("\nДетали несовпадений:\n")
        for idx, row in inconsistencies_df.iterrows():
            print(f"Артикул: {row['sku']}")
            print(f"  Названия товаров: {row['product_names']}")
            print(f"  Количество вариантов: {row['count_variants']}")
            print(f"  Всего записей: {row['records_count']}")
            print()

        return {
            "total_skus": total_skus,
            "inconsistent_count": inconsistent_count,
            "inconsistent_data": inconsistencies_df,
        }

    print("=" * 80)
    return {
        "total_skus": total_skus,
        "inconsistent_count": 0,
        "inconsistent_data": pd.DataFrame(),
    }


if __name__ == "__main__":
    from datetime import datetime

    # Путь к файлу данных
    data_path = Path("data/clean/sales_data.csv")
    output_path = Path("data/clean")

    # Проверяем наличие файла
    if not data_path.exists():
        print(f"❌ Ошибка: файл {data_path} не найден!")
        exit(1)

    # Выполняем проверку
    results = check_product_consistency(str(data_path))

    # Сохраняем результаты, если есть несовпадения
    if results["inconsistent_count"] > 0:
        output_file = output_path / "product_inconsistencies.csv"
        results["inconsistent_data"].to_csv(output_file, index=False, encoding="utf-8")
        print(f"\n📁 Отчёт о несовпадениях сохранён в: {output_file}")

    # Итоговый отчёт
    print(f"\n📈 Итоговая статистика:")
    print(f"  • Всего уникальных артикулов: {results['total_skus']}")
    print(f"  • Артикулов с несовпадениями: {results['inconsistent_count']}")
    print(
        f"  • Процент корректных: {((results['total_skus'] - results['inconsistent_count']) / results['total_skus'] * 100):.1f}%"
    )
    print(f"\n⏰ Проверка выполнена: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}")
