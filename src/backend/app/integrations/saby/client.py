from datetime import datetime
from typing import Any, Literal

import httpx
from fastapi import HTTPException, status

from src.backend.app.core.config import Settings


class SabyClient:
    """Async wrapper for Saby APIs.

    - Retail HTTP API: ``GET {saby_api_base_url}/retail/...`` (X-SBISAccessToken).
    - Service JSON-RPC: ``POST {saby_service_url}`` with JSON-RPC 2.0 body
      (e.g. ``sabyWarehouse.List``), same token header.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._cached_token: str | None = settings.saby_access_token

    async def list_sales_points(
        self,
        product: str = "retail",
        page: int = 0,
        page_size: int = 100,
    ) -> dict[str, Any]:
        return await self._get(
            "/retail/point/list",
            params={"product": product, "page": page, "pageSize": page_size},
        )

    async def list_products(
        self,
        point_id: int | None = None,
        price_list_id: int | None = None,
        warehouse_id: str | None = None,
        no_stop_list: bool | None = None,
        search_string: str | None = None,
        with_balance: bool = True,
        with_barcode: bool | None = None,
        page: int = 0,
        page_size: int = 100,
        position: int | None = None,
        order: Literal["before", "after"] | None = None,
    ) -> dict[str, Any]:
        """GET ``/retail/v2/nomenclature/list`` — каталог / номенклатура (Saby Retail).

        Документация: https://saby.ru/help/integration/api/app_sale/sale_delyvery/catalog
        """

        params: dict[str, Any] = {
            "withBalance": str(with_balance).lower(),
            "page": page,
            "pageSize": page_size,
        }
        if point_id is not None:
            params["pointId"] = point_id
        if price_list_id is not None:
            params["priceListId"] = price_list_id
        if warehouse_id is not None:
            params["warehouseId"] = warehouse_id
        if no_stop_list is not None:
            params["noStopList"] = str(no_stop_list).lower()
        if search_string is not None:
            params["searchString"] = search_string
        if with_barcode is not None:
            params["withBarcode"] = str(with_barcode).lower()
        if position is not None:
            params["position"] = position
        if order is not None:
            params["order"] = order

        return await self._get("/retail/v2/nomenclature/list", params=params)

    async def list_balances(
        self,
        company_ids: list[int],
        warehouse_ids: list[int],
        nomenclature_ids: list[int] | None = None,
        price_list_ids: list[int] | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "companies": company_ids,
            "warehouses": warehouse_ids,
        }
        if nomenclature_ids:
            params["nomenclatures"] = nomenclature_ids
        if price_list_ids:
            params["priceListIds"] = price_list_ids

        return await self._get("/retail/nomenclature/balances", params=params)

    async def list_sales(
        self,
        from_datetime: datetime,
        to_datetime: datetime | None = None,
        point_id: int | None = None,
        page: int = 0,
        page_size: int = 100,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "fromDateTime": from_datetime.strftime("%Y-%m-%d %H:%M:%S"),
            "page": page,
            "pageSize": page_size,
        }
        if to_datetime is not None:
            params["toDateTime"] = to_datetime.strftime("%Y-%m-%d %H:%M:%S")
        if point_id is not None:
            params["pointId"] = point_id

        return await self._get("/retail/order/list", params=params)

    async def price_list(
        self,
        point_id: int,
        actual_date: datetime,
        page: int = 0,
        page_size: int = 100,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "page": page,
            "pageSize": page_size,
            "pointId": point_id,
            "actualDate": actual_date.strftime("%Y-%m-%d"),
        }
        return await self._get("/retail/nomenclature/price-list", params=params)


    async def list_warehouses(
        self,
        page: int = 0,
        limit: int = 100,
        filter_extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """JSON-RPC ``sabyWarehouse.List`` — список складов без иерархии.

        Документация: https://saby.ru/help/integration/api/inventory/sabywarehouse_list
        Параметры ``page`` и ``limit`` передаются внутри обязательного ``filter``.
        """
        flt: dict[str, Any] = {"page": page, "limit": limit}
        if filter_extra:
            for key, value in filter_extra.items():
                if value is not None:
                    flt[key] = value
        return await self._jsonrpc("sabyWarehouse.List", {"filter": flt})

    async def _jsonrpc(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        request_id: int = 1,
    ) -> dict[str, Any]:
        """POST JSON-RPC 2.0 к ``saby_service_url`` (``online.sbis.ru/service/``)."""
        token = await self._get_access_token()
        body: dict[str, Any] = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params or {},
            "id": request_id,
        }
        headers = {
            "X-SBISAccessToken": token,
            "Content-Type": "application/json-rpc;charset=utf-8",
        }
        service_url = str(self._settings.saby_service_url).rstrip("/") + "/"

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(service_url, json=body, headers=headers)

            if response.status_code == status.HTTP_401_UNAUTHORIZED:
                self._cached_token = None
                token = await self._get_access_token()
                headers["X-SBISAccessToken"] = token
                response = await client.post(service_url, json=body, headers=headers)

        if response.is_error:
            raise HTTPException(
                status_code=response.status_code,
                detail={
                    "message": "Saby JSON-RPC request failed",
                    "method": method,
                    "response": response.text,
                },
            )
        data = response.json()
        if not isinstance(data, dict):
            return {"result": data}
        err = data.get("error")
        if err:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={
                    "message": "Saby JSON-RPC error",
                    "method": method,
                    "error": err,
                },
            )
        return data

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        token = await self._get_access_token()
        headers = {"X-SBISAccessToken": token}

        async with httpx.AsyncClient(
            base_url=self._settings.saby_api_base_url,
            timeout=30.0,
        ) as client:
            response = await client.get(path, params=params, headers=headers)

            if response.status_code == status.HTTP_401_UNAUTHORIZED:
                self._cached_token = None
                token = await self._get_access_token()
                headers["X-SBISAccessToken"] = token
                response = await client.get(path, params=params, headers=headers)

        if response.is_error:
            raise HTTPException(
                status_code=response.status_code,
                detail={
                    "message": "Saby API request failed",
                    "response": response.text,
                },
            )
        return response.json()

    async def _get_access_token(self) -> str:
        if self._cached_token:
            return self._cached_token

        if not (
            self._settings.saby_app_client_id
            and self._settings.saby_app_secret
            and self._settings.saby_secret_key
        ):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=(
                    "Saby credentials are not configured. Fill SABY_APP_CLIENT_ID, "
                    "SABY_APP_SECRET, and SABY_SECRET_KEY in src/backend/.env."
                ),
            )

        payload = {
            "app_client_id": self._settings.saby_app_client_id,
            "app_secret": self._settings.saby_app_secret,
            "secret_key": self._settings.saby_secret_key,
        }
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(self._settings.saby_auth_url, json=payload)

        if response.is_error:
            raise HTTPException(
                status_code=response.status_code,
                detail={
                    "message": "Saby authorization failed",
                    "response": response.text,
                },
            )

        data = response.json()
        token = data.get("token") or data.get("access_token")
        
        if not token:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Saby authorization response does not contain token.",
            )
            
        # 3. Сохраняем полученный токен в наш кэш!
        self._cached_token = str(token)
        
        return self._cached_token
