import xlrd
import xlwt
from xlutils.copy import copy
from collections import Counter
from pathlib import Path

def _find_header_row_export(sh: xlrd.sheet.Sheet) -> int:
    scan = min(80, sh.nrows)
    for r in range(scan):
        row_vals = {str(sh.cell_value(r, c)).strip() for c in range(sh.ncols)}
        if {"УКП", "КОД Продаж"} <= row_vals:
            return r
    raise ValueError("Header row not found")

def export_order_to_xls(template_path: str | Path, output_path: str | Path, order_data: dict[str, int]) -> None:
    """
    order_data: dict mapping article to quantity
    """
    rb = xlrd.open_workbook(str(template_path), formatting_info=True)
    
    # Locate the target sheet
    try:
        sh_idx = rb.sheet_names().index("Бланк заказа")
    except ValueError:
        sh_idx = 0
    
    sh = rb.sheet_by_index(sh_idx)
    hdr_row = _find_header_row_export(sh)
    
    col_map = {}
    for c in range(sh.ncols):
        key = str(sh.cell_value(hdr_row, c)).strip()
        if key:
            col_map[key] = c
            
    target_col = col_map.get("Заявка, короба") or col_map.get("Заявка, шт.")
    if target_col is None:
        raise ValueError("Could not find order quantity column (Заявка, короба / Заявка, шт.)")
        
    ukp_i = col_map["УКП"]
    kod_i = col_map.get("КОД Продаж", ukp_i)
    
    # Copy workbook to make it writable
    wb = copy(rb)
    w_sh = wb.get_sheet(sh_idx)
    
    # Calculate duplicates to map rows properly (just like in ingestion)
    ukp_counts = Counter()
    for r in range(hdr_row + 1, sh.nrows):
        ukp = str(sh.cell_value(r, ukp_i)).strip()
        if ukp:
            ukp_counts[ukp] += 1
            
    # Iterate and write
    for r in range(hdr_row + 1, sh.nrows):
        ukp = str(sh.cell_value(r, ukp_i)).strip()
        if not ukp:
            continue
        kod = str(sh.cell_value(r, kod_i)).strip()
        
        # determine article
        if ukp_counts[ukp] > 1:
            article = kod or ukp
        else:
            article = ukp
            
        if article in order_data:
            qty = order_data[article]
            if qty is not None and qty > 0:
                w_sh.write(r, target_col, qty)
                
    wb.save(str(output_path))
