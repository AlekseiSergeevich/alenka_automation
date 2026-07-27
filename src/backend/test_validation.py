import asyncio
from src.backend.app.integrations.saby.schemas import ProductBalanceSchema

def main():
    try:
        ProductBalanceSchema.model_validate({"name": None, "article": "123"})
        print("Success")
    except Exception as e:
        print(f"Failed: {e}")

if __name__ == "__main__":
    main()
