"""Загрузка и статус ежемесячного бланка заказа (.xls)."""

from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from src.backend.app.api.deps import require_admin, require_user
from src.backend.app.core.config import Settings, get_settings
from src.backend.app.core.security import AuthUser
from src.backend.app.db.session import get_session
from src.backend.app.ingestion.order_blank import parse_order_blank
from src.backend.app.models import OrderBlankUpload
from src.backend.app.services.aggregate import refresh_aggregate
from src.backend.app.services.order_blank_catalog import (
    STATUS_FAILED,
    STATUS_SUCCESS,
    apply_order_blank_full_sync,
    compute_order_blank_reminder_state,
    utc_now,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/order-blank", tags=["order-blank"])

_MAX_BYTES = 25 * 1024 * 1024


class OrderBlankStatusResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    product_count: int
    catalog_empty: bool
    needs_monthly_upload: bool
    needs_order_blank: bool
    last_success_applied_at: datetime | None = None
    warning: str | None = None


class OrderBlankUploadResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int
    row_count: int
    applied_at: datetime
    content_sha256: str
    stored_path: str
    original_filename: str


def _blank_warning_for_state(catalog_empty: bool, needs_monthly: bool) -> str | None:
    if catalog_empty:
        return (
            "Справочник товаров пуст; загрузите бланк заказа (.xls), чтобы включить "
            "синхронизацию остатков и продаж."
        )
    if needs_monthly:
        return (
            "В текущем месяце ещё не загружен актуальный бланк заказа (.xls). "
            "Загрузите файл, чтобы обновить каталог."
        )
    return None


@router.get("/status", response_model=OrderBlankStatusResponse)
async def order_blank_status(
    _: AuthUser = Depends(require_user),
    session: AsyncSession = Depends(get_session),
) -> OrderBlankStatusResponse:
    hint = await compute_order_blank_reminder_state(session)
    return OrderBlankStatusResponse(
        product_count=hint.product_count,
        catalog_empty=hint.catalog_empty,
        needs_monthly_upload=hint.needs_monthly_upload,
        needs_order_blank=hint.needs_order_blank_attention,
        last_success_applied_at=hint.last_success_applied_at,
        warning=_blank_warning_for_state(hint.catalog_empty, hint.needs_monthly_upload),
    )


def _sanitize_stub(name: str) -> str:
    base = Path(name).name
    stem = Path(base).stem
    cleaned = re.sub(r"[^\w.\-]+", "_", stem, flags=re.UNICODE).strip("._")
    return (cleaned[:80] or "blank")


async def _persist_failed_upload(
    session: AsyncSession,
    *,
    original_filename: str,
    stored_path: str,
    content_sha256: str,
    message: str,
) -> None:
    rec = OrderBlankUpload(
        original_filename=original_filename[:512],
        stored_path=stored_path[:1024],
        content_sha256=content_sha256,
        uploaded_at=utc_now(),
        applied_at=None,
        row_count=0,
        status=STATUS_FAILED,
        error_message=message[:8000],
    )
    session.add(rec)


@router.post("/upload", response_model=OrderBlankUploadResponse)
async def order_blank_upload(
    _: AuthUser = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    file: UploadFile = File(..., description="Файл бланка заказа (.xls)"),
) -> OrderBlankUploadResponse:
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Filename is required",
        )
    if not (file.filename.lower().endswith(".xls") or file.filename.lower().endswith(".xlsx")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only .xls and .xlsx files are supported",
        )

    content = await file.read()
    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Empty file",
        )
    if len(content) > _MAX_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File too large",
        )

    digest = hashlib.sha256(content).hexdigest()
    storage_root = Path(settings.order_blank_storage_dir).expanduser().resolve()
    storage_root.mkdir(parents=True, exist_ok=True)

    ts = utc_now().strftime("%Y%m%dT%H%M%SZ")
    stub = _sanitize_stub(file.filename)
    ext = Path(file.filename).suffix.lower()
    stored_name = f"{ts}_{digest[:16]}_{stub}{ext}"
    abs_path = storage_root / stored_name
    abs_path.write_bytes(content)
    # Храним путь относительно корня хранилища (один каталог).
    rel_stored = stored_name

    original = Path(file.filename).name[:512]

    try:
        rows, articles = parse_order_blank(abs_path)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Order blank parse failed: %s", exc)
        async with session.begin():
            await _persist_failed_upload(
                session,
                original_filename=original,
                stored_path=rel_stored,
                content_sha256=digest,
                message=f"parse_error: {exc}",
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid order blank file: {exc}",
        ) from exc

    if not articles:
        async with session.begin():
            await _persist_failed_upload(
                session,
                original_filename=original,
                stored_path=rel_stored,
                content_sha256=digest,
                message="parse_ok_but_no_articles",
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No product rows with УКП found in file",
        )

    applied_at = utc_now()
    async with session.begin():
        n = await apply_order_blank_full_sync(
            session, rows, articles, now=applied_at
        )
        await refresh_aggregate(session, store_id=None)
        rec = OrderBlankUpload(
            original_filename=original,
            stored_path=rel_stored,
            content_sha256=digest,
            uploaded_at=applied_at,
            applied_at=applied_at,
            row_count=n,
            status=STATUS_SUCCESS,
            error_message=None,
        )
        session.add(rec)
        await session.flush()

        from sqlalchemy.dialects.postgresql import insert as pg_insert
        from src.backend.app.models.order_blank_item import OrderBlankItem

        items_to_insert = []
        for r in rows:
            is_new_val = 1 if r["feature"] == "Новинка" else 0
            focus_val = str(r["focus"]).strip() if r["focus"] else "Прочее"
            if not focus_val:
                focus_val = "Прочее"
            abc_val = str(r["group_abc"]).strip() if r["group_abc"] else "Unknown"
            if not abc_val:
                abc_val = "Unknown"
            item_type_val = str(r["type"]).strip() if r["type"] else "Unknown"
            if not item_type_val:
                item_type_val = "Unknown"
            brand_val = str(r.get("brand")).strip() if r.get("brand") else "Unknown"
            if not brand_val or brand_val == "None":
                brand_val = "Unknown"

            items_to_insert.append({
                "upload_id": rec.id,
                "sku": r["article"],
                "name": r["name"],
                "is_new": is_new_val,
                "focus": focus_val,
                "abc_group": abc_val,
                "item_type": item_type_val,
                "brand": brand_val,
                "base_price": r.get("base_price", 0),
                "shelf_life_days": r.get("shelf_life_days", 0),
                "weight_gr": r.get("weight_gr", 0),
            })

        if items_to_insert:
            stmt = pg_insert(OrderBlankItem).values(items_to_insert)
            await session.execute(stmt)

    oid = rec.id
    assert oid is not None

    return OrderBlankUploadResponse(
        id=int(oid),
        row_count=n,
        applied_at=applied_at,
        content_sha256=digest,
        stored_path=rel_stored,
        original_filename=original,
    )

from src.backend.app.services.order_export import export_order_to_xls
from fastapi.responses import FileResponse
from pydantic import BaseModel
import tempfile

class OrderExportRequest(BaseModel):
    store_id: int
    orders: dict[str, int]

@router.post("/export")
async def export_order(
    req: OrderExportRequest,
    session: AsyncSession = Depends(get_session)
):
    from src.backend.app.ingestion.order_blank import find_latest_order_blank_xls, project_root_from_here
    
    root = project_root_from_here()
    template_path = find_latest_order_blank_xls(root)
    if not template_path:
        raise HTTPException(status_code=404, detail="Нет загруженного бланка заказа")
        
    out_file = tempfile.NamedTemporaryFile(delete=False, suffix=".xls")
    out_file.close()
    
    export_order_to_xls(template_path, out_file.name, req.orders)
    
    return FileResponse(
        out_file.name, 
        media_type="application/vnd.ms-excel",
        filename=f"order_store_{req.store_id}.xls"
    )

