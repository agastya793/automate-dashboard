"""
Generic Excel Bounds Detection & Ghost-Row Protection Module.

Identifies the meaningful analytical data boundary of an Excel worksheet
and separates the physical declared range from the effective data range.
Protects ingestion against bloated worksheets containing hundreds of thousands
of accidental fill-down formula error rows (e.g. #DIV/0!) while strictly
preserving legitimate large datasets (e.g. 100,000+ real records).
"""

from __future__ import annotations

import io
import re
import xml.etree.ElementTree as ET
import xml.parsers.expat
import zipfile
from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class SheetBounds:
    """
    Metadata capturing physical vs effective data boundaries of a worksheet.
    """
    sheet_name: str
    physical_max_row: int
    physical_max_col: int
    effective_data_max_row: int
    effective_data_max_col: int
    ignored_trailing_rows: int
    detection_reason: Optional[str] = None
    warning_message: Optional[str] = None
    has_ghost_tail: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "sheet_name": self.sheet_name,
            "physical_max_row": self.physical_max_row,
            "physical_max_col": self.physical_max_col,
            "effective_data_max_row": self.effective_data_max_row,
            "effective_data_max_col": self.effective_data_max_col,
            "ignored_trailing_rows": self.ignored_trailing_rows,
            "detection_reason": self.detection_reason,
            "warning_message": self.warning_message,
            "has_ghost_tail": self.has_ghost_tail,
        }


def col_letter_to_index(col_str: str) -> int:
    """Convert column letters (e.g. 'A', 'Z', 'AA', 'DPT') to 1-based index."""
    idx = 0
    for char in col_str.upper():
        if "A" <= char <= "Z":
            idx = idx * 26 + (ord(char) - ord("A") + 1)
    return max(idx, 1)


def parse_range_max(ref_str: str) -> tuple[int, int]:
    """Parse Excel range ref (e.g. 'A1:AG573424') to (max_row, max_col) 1-based."""
    parts = ref_str.split(":")
    end_cell = parts[-1]
    m = re.match(r"([A-Za-z]+)(\d+)", end_cell)
    if m:
        return int(m.group(2)), col_letter_to_index(m.group(1))
    return 1, 1


# Minimum trailing gap to even consider ghost classification (conservative safety)
GHOST_TAIL_MIN_ROWS: int = 50


class _XmlSheetBoundsParser:
    """
    Fast, streaming expat XML parser for OpenXML worksheet XML.
    Extracts physical range, merged cells, autofilters, and the last solid data row
    in a single C-level pass without materialising Python objects for all cells.
    """
    def __init__(self, sheet_name: str):
        self.sheet_name = sheet_name
        self.declared_max_row = 1
        self.declared_max_col = 1
        self.merge_max_row = 1
        self.autofilter_max_row = 1
        self.last_solid_data_row = 0
        self.last_any_cell_row = 0
        self.highest_col_seen = 1

        self.current_row = 0
        self.row_cell_count = 0
        self.row_has_solid_cell = False

        self.current_cell_type = ""
        self.in_val_tag = False
        self.current_val_chars: list[str] = []

    def start_element(self, name: str, attrs: dict[str, str]) -> None:
        if name == "dimension" or name.endswith("}dimension"):
            ref = attrs.get("ref", "")
            if ref:
                self.declared_max_row, self.declared_max_col = parse_range_max(ref)
        elif name == "mergeCell" or name.endswith("}mergeCell"):
            ref = attrs.get("ref", "")
            if ref:
                r, c = parse_range_max(ref)
                if r > self.merge_max_row:
                    self.merge_max_row = r
                if c > self.highest_col_seen:
                    self.highest_col_seen = c
        elif name == "autoFilter" or name.endswith("}autoFilter"):
            ref = attrs.get("ref", "")
            if ref:
                r, c = parse_range_max(ref)
                if r > self.autofilter_max_row:
                    self.autofilter_max_row = r
                if c > self.highest_col_seen:
                    self.highest_col_seen = c
        elif name == "row" or name.endswith("}row"):
            r_num = int(attrs.get("r", 0))
            self.current_row = r_num
            if r_num > self.last_any_cell_row:
                self.last_any_cell_row = r_num
            self.row_cell_count = 0
            self.row_has_solid_cell = False
        elif name == "c" or name.endswith("}c"):
            self.row_cell_count += 1
            c_ref = attrs.get("r", "")
            self.current_cell_type = attrs.get("t", "")
            m = re.match(r"([A-Za-z]+)", c_ref)
            if m:
                c_idx = col_letter_to_index(m.group(1))
                if c_idx > self.highest_col_seen:
                    self.highest_col_seen = c_idx
        elif name in ("v", "t") or name.endswith("}v") or name.endswith("}t"):
            self.in_val_tag = True
            self.current_val_chars = []

    def char_data(self, data: str) -> None:
        if self.in_val_tag:
            self.current_val_chars.append(data)

    def end_element(self, name: str) -> None:
        if name in ("v", "t") or name.endswith("}v") or name.endswith("}t"):
            self.in_val_tag = False
            text = "".join(self.current_val_chars).strip()
            # A solid cell has a non-error type, and non-empty, non-error text
            if self.current_cell_type != "e" and text != "" and not text.startswith("#"):
                self.row_has_solid_cell = True
        elif name == "row" or name.endswith("}row"):
            # Solid row criteria:
            # 1. Contains a cell with a real non-empty value
            # 2. OR contains cells across multiple columns (structured tabular row)
            # 3. OR falls within merged cells or autofilter range
            if (
                self.row_has_solid_cell
                or self.row_cell_count > 1
                or self.current_row <= self.merge_max_row
                or self.current_row <= self.autofilter_max_row
            ):
                if self.current_row > self.last_solid_data_row:
                    self.last_solid_data_row = self.current_row


def detect_sheet_bounds_from_xml(
    zf: zipfile.ZipFile,
    sheet_xml_path: str,
    sheet_name: str,
    drawing_max_row: int = 1,
) -> SheetBounds:
    """
    Examine a worksheet XML part in an XLSX zip archive and determine its
    physical and effective boundaries.
    """
    parser = _XmlSheetBoundsParser(sheet_name)
    p = xml.parsers.expat.ParserCreate()
    p.StartElementHandler = parser.start_element
    p.EndElementHandler = parser.end_element
    p.CharacterDataHandler = parser.char_data

    with zf.open(sheet_xml_path) as f:
        p.ParseFile(f)

    physical_max_r = max(parser.declared_max_row, parser.last_any_cell_row, 1)
    physical_max_c = max(parser.declared_max_col, parser.highest_col_seen, 1)

    min_safe_row = max(
        parser.last_solid_data_row,
        parser.merge_max_row,
        parser.autofilter_max_row,
        drawing_max_row,
        1,
    )

    trailing_ghost_rows = physical_max_r - min_safe_row

    # Conservative ghost classification:
    # 1. Must have at least GHOST_TAIL_MIN_ROWS trailing rows.
    # 2. Total physical rows must be substantial (> 100 rows).
    # 3. The trailing rows are > 10% of physical height, or >= 500 rows.
    # 4. No multi-column or solid data exists beyond min_safe_row.
    if (
        trailing_ghost_rows >= GHOST_TAIL_MIN_ROWS
        and physical_max_r > 100
        and (trailing_ghost_rows >= 500 or (trailing_ghost_rows / physical_max_r) > 0.10)
    ):
        effective_max_r = min_safe_row
        ignored = trailing_ghost_rows
        reason = (
            f"Detected {ignored:,} trailing ghost/fill-down formula rows "
            f"(rows {effective_max_r + 1} to {physical_max_r}) beyond valid data "
            f"boundary at row {effective_max_r}."
        )
        warning = (
            f'Large trailing formula range detected on "{sheet_name}". '
            f"{ignored:,} non-data rows were excluded from analysis. "
            f"The original workbook was not modified."
        )
        has_ghost = True
    else:
        effective_max_r = physical_max_r
        ignored = 0
        reason = None
        warning = None
        has_ghost = False

    return SheetBounds(
        sheet_name=sheet_name,
        physical_max_row=physical_max_r,
        physical_max_col=physical_max_c,
        effective_data_max_row=effective_max_r,
        effective_data_max_col=physical_max_c,
        ignored_trailing_rows=ignored,
        detection_reason=reason,
        warning_message=warning,
        has_ghost_tail=has_ghost,
    )


def detect_all_sheet_bounds(raw: bytes) -> dict[str, SheetBounds]:
    """
    Inspect raw XLSX bytes and return a mapping of sheet_name -> SheetBounds.
    Runs in milliseconds for typical workbooks and ~10s for 500k-row XMLs.
    If the bytes are not an XLSX zip archive, returns an empty dict.
    """
    bounds_map: dict[str, SheetBounds] = {}
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            namelist = set(zf.namelist())
            if "xl/workbook.xml" not in namelist:
                return bounds_map

            wb_tree = ET.fromstring(zf.read("xl/workbook.xml"))
            rel_map: dict[str, str] = {}
            if "xl/_rels/workbook.xml.rels" in namelist:
                wb_rels = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
                for r in wb_rels.findall("{http://schemas.openxmlformats.org/package/2006/relationships}Relationship"):
                    rel_map[r.attrib["Id"]] = r.attrib["Target"]

            # Map drawings to max row anchors if present
            drawing_anchors: dict[str, int] = {}
            for n in namelist:
                if n.startswith("xl/drawings/drawing") and not n.endswith(".rels"):
                    try:
                        d_tree = ET.fromstring(zf.read(n))
                        # find to/row
                        for row_elem in d_tree.findall(".//{http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing}to/{http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing}row"):
                            if row_elem.text:
                                drawing_anchors[n] = max(drawing_anchors.get(n, 1), int(row_elem.text) + 1)
                    except Exception:
                        pass

            sheets_elem = wb_tree.find("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}sheets")
            if sheets_elem is None:
                return bounds_map

            for s in sheets_elem.findall("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}sheet"):
                s_name = s.attrib["name"]
                r_id = s.attrib.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id", "")
                target = rel_map.get(r_id, "")
                if not target:
                    continue
                clean_target = target.lstrip("/")
                xml_path = clean_target if clean_target.startswith("xl/") else "xl/" + clean_target
                if xml_path not in namelist:
                    continue

                # Find associated drawing max row
                target_base = clean_target.split("/")[-1]
                sheet_rels_path = f"xl/worksheets/_rels/{target_base}.rels"
                sheet_draw_max = 1
                if sheet_rels_path in namelist:
                    try:
                        s_rels = ET.fromstring(zf.read(sheet_rels_path))
                        for rel in s_rels.findall("{http://schemas.openxmlformats.org/package/2006/relationships}Relationship"):
                            if "drawing" in rel.attrib.get("Type", ""):
                                d_target = rel.attrib.get("Target", "").lstrip("/").split("/")[-1]
                                d_full = "xl/drawings/" + d_target
                                sheet_draw_max = max(sheet_draw_max, drawing_anchors.get(d_full, 1))
                    except Exception:
                        pass

                bounds = detect_sheet_bounds_from_xml(
                    zf=zf,
                    sheet_xml_path=xml_path,
                    sheet_name=s_name,
                    drawing_max_row=sheet_draw_max,
                )
                bounds_map[s_name] = bounds

    except Exception:
        # Failsafe: return whatever could be parsed without raising
        pass

    return bounds_map


def detect_openpyxl_sheet_bounds(ws: Any) -> SheetBounds:
    """
    Fallback inspector for an openpyxl Worksheet object (e.g. in unit tests
    or mock environments without zip bytes).
    """
    sheet_name = getattr(ws, "title", "Sheet")
    physical_max_r = getattr(ws, "max_row", 1) or 1
    physical_max_c = getattr(ws, "max_column", 1) or 1

    # Check merged cells
    merge_max_r = 1
    for m in getattr(ws, "merged_cells", []):
        if hasattr(m, "max_row") and m.max_row:
            merge_max_r = max(merge_max_r, m.max_row)

    # Check autofilter
    af_max_r = 1
    af = getattr(ws, "auto_filter", None)
    if af and getattr(af, "ref", None):
        r, _ = parse_range_max(af.ref)
        af_max_r = max(af_max_r, r)

    # If small sheet, bounds match physical
    if physical_max_r <= GHOST_TAIL_MIN_ROWS:
        return SheetBounds(
            sheet_name=sheet_name,
            physical_max_row=physical_max_r,
            physical_max_col=physical_max_c,
            effective_data_max_row=physical_max_r,
            effective_data_max_col=physical_max_c,
            ignored_trailing_rows=0,
            has_ghost_tail=False,
        )

    # Scan rows upwards from max_row to find the true solid data boundary
    last_solid_r = max(merge_max_r, af_max_r, 1)

    # Sample rows from max_row backwards to find solid data
    for r in range(physical_max_r, max(last_solid_r, 1) - 1, -1):
        row_vals = [ws.cell(row=r, column=c).value for c in range(1, min(physical_max_c + 1, 30))]
        non_empty = [v for v in row_vals if v is not None and str(v).strip() != ""]
        non_errors = [v for v in non_empty if not (isinstance(v, str) and v.startswith("#"))]

        # Solid if:
        # - Has non-error value
        # - OR has > 1 non-empty cells
        if len(non_errors) > 0 or len(non_empty) > 1:
            last_solid_r = max(last_solid_r, r)
            break

    min_safe_row = max(last_solid_r, merge_max_r, af_max_r, 1)
    trailing_ghost_rows = physical_max_r - min_safe_row

    if (
        trailing_ghost_rows >= GHOST_TAIL_MIN_ROWS
        and physical_max_r > 100
        and (trailing_ghost_rows >= 500 or (trailing_ghost_rows / physical_max_r) > 0.10)
    ):
        effective_max_r = min_safe_row
        ignored = trailing_ghost_rows
        reason = (
            f"Detected {ignored:,} trailing ghost/fill-down formula rows "
            f"(rows {effective_max_r + 1} to {physical_max_r}) beyond valid data "
            f"boundary at row {effective_max_r}."
        )
        warning = (
            f'Large trailing formula range detected on "{sheet_name}". '
            f"{ignored:,} non-data rows were excluded from analysis. "
            f"The original workbook was not modified."
        )
        has_ghost = True
    else:
        effective_max_r = physical_max_r
        ignored = 0
        reason = None
        warning = None
        has_ghost = False

    return SheetBounds(
        sheet_name=sheet_name,
        physical_max_row=physical_max_r,
        physical_max_col=physical_max_c,
        effective_data_max_row=effective_max_r,
        effective_data_max_col=physical_max_c,
        ignored_trailing_rows=ignored,
        detection_reason=reason,
        warning_message=warning,
        has_ghost_tail=has_ghost,
    )
