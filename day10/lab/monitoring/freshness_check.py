"""
Freshness check — đo SLA tại 2 boundary (BONUS +1đ):

  Boundary 1 — INGEST:   latest_exported_at trong manifest
                          (thời điểm dữ liệu được trích xuất từ hệ thống nguồn)
  Boundary 2 — PUBLISH:  run_timestamp trong manifest
                          (thời điểm pipeline hoàn tất và đẩy lên vector store)

Kết quả tổng hợp: PASS nếu cả 2 boundary đều trong SLA.
                  WARN nếu chỉ 1 boundary vượt SLA.
                  FAIL nếu cả 2 boundary đều vượt SLA hoặc thiếu timestamp.

Log minh chứng đầy đủ: ingest_age_hours, publish_age_hours, sla_hours.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _parse_iso(ts: str) -> Optional[datetime]:
    """
    Parse timestamp ở nhiều định dạng:
      - ISO-8601 chuẩn: YYYY-MM-DDTHH:MM:SS[Z|+offset]
      - Slash date:     YYYY/MM/DDTHH:MM:SS  (thường gặp trong export cũ)
      - Date only:      YYYY-MM-DD hoặc YYYY/MM/DD
    """
    if not ts:
        return None
    s = ts.strip()
    # Chuẩn hoá: thay dấu / thành - trong phần ngày (trước 'T' hoặc toàn bộ)
    if "/" in s:
        parts = s.split("T", 1)
        parts[0] = parts[0].replace("/", "-")
        s = "T".join(parts)
    s = s.replace("Z", "+00:00")
    # Thêm giờ nếu chỉ có ngày
    if len(s) == 10:
        s += "T00:00:00+00:00"
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def _age_hours(dt: datetime, now: datetime) -> float:
    """Trả về số giờ kể từ dt đến now (non-negative)."""
    delta = now - dt
    return max(0.0, round(delta.total_seconds() / 3600.0, 3))


def _sla_status(age_hours: float, sla_hours: float) -> str:
    """PASS nếu trong SLA, FAIL nếu vượt."""
    return "PASS" if age_hours <= sla_hours else "FAIL"


# ---------------------------------------------------------------------------
# API chính
# ---------------------------------------------------------------------------

def check_manifest_freshness(
    manifest_path: Path,
    *,
    sla_hours: float = 24.0,
    now: Optional[datetime] = None,
) -> Tuple[str, Dict[str, Any]]:
    """
    Đọc manifest và đo freshness tại 2 boundary.

    Trả về ("PASS" | "WARN" | "FAIL", detail_dict).

    detail_dict chứa:
      - boundary_ingest  : {timestamp, age_hours, sla_hours, status}
      - boundary_publish : {timestamp, age_hours, sla_hours, status}
      - overall_status   : PASS / WARN / FAIL
      - summary          : chuỗi mô tả ngắn
    """
    now = now or datetime.now(timezone.utc)

    if not manifest_path.is_file():
        detail = {
            "reason": "manifest_missing",
            "path": str(manifest_path),
            "overall_status": "FAIL",
            "summary": "Manifest file not found",
        }
        return "FAIL", detail

    try:
        data: Dict[str, Any] = json.loads(
            manifest_path.read_text(encoding="utf-8")
        )
    except json.JSONDecodeError as exc:
        return "FAIL", {"reason": "manifest_parse_error", "error": str(exc)}

    # ── Boundary 1: INGEST (thời điểm data xuất ra từ source) ────────────────
    ingest_ts_raw = data.get("latest_exported_at") or ""
    ingest_dt = _parse_iso(str(ingest_ts_raw)) if ingest_ts_raw else None
    if ingest_dt:
        ingest_age = _age_hours(ingest_dt, now)
        ingest_status = _sla_status(ingest_age, sla_hours)
        boundary_ingest = {
            "boundary": "ingest",
            "timestamp": ingest_ts_raw,
            "age_hours": ingest_age,
            "sla_hours": sla_hours,
            "status": ingest_status,
            "description": "Thời điểm dữ liệu được trích xuất từ hệ thống nguồn (exported_at)",
        }
    else:
        ingest_status = "WARN"
        boundary_ingest = {
            "boundary": "ingest",
            "timestamp": ingest_ts_raw,
            "age_hours": None,
            "sla_hours": sla_hours,
            "status": "WARN",
            "description": "Không có trường latest_exported_at trong manifest",
        }

    # ── Boundary 2: PUBLISH (thời điểm pipeline hoàn tất và push lên Chroma) ─
    publish_ts_raw = data.get("run_timestamp") or ""
    publish_dt = _parse_iso(str(publish_ts_raw)) if publish_ts_raw else None
    if publish_dt:
        publish_age = _age_hours(publish_dt, now)
        publish_status = _sla_status(publish_age, sla_hours)
        boundary_publish = {
            "boundary": "publish",
            "timestamp": publish_ts_raw,
            "age_hours": publish_age,
            "sla_hours": sla_hours,
            "status": publish_status,
            "description": "Thời điểm pipeline hoàn tất và đẩy lên vector store (run_timestamp)",
        }
    else:
        publish_status = "WARN"
        boundary_publish = {
            "boundary": "publish",
            "timestamp": publish_ts_raw,
            "age_hours": None,
            "sla_hours": sla_hours,
            "status": "WARN",
            "description": "Không có trường run_timestamp trong manifest",
        }

    # ── Tổng hợp overall status ───────────────────────────────────────────────
    statuses = {ingest_status, publish_status}

    if statuses == {"PASS"}:
        overall = "PASS"
        summary = (
            f"Cả 2 boundary trong SLA ({sla_hours}h): "
            f"ingest={boundary_ingest.get('age_hours')}h, "
            f"publish={boundary_publish.get('age_hours')}h"
        )
    elif "FAIL" in statuses and len(statuses) == 1:
        overall = "FAIL"
        summary = f"Cả 2 boundary VƯỢT SLA ({sla_hours}h) — cần chạy lại pipeline"
    elif "FAIL" in statuses:
        overall = "WARN"
        summary = (
            f"Một boundary vượt SLA ({sla_hours}h): "
            f"ingest={ingest_status}, publish={publish_status}"
        )
    else:
        # Có WARN (thiếu timestamp) nhưng không FAIL
        overall = "WARN"
        summary = "Một hoặc hai boundary thiếu timestamp — không thể đo đầy đủ"

    detail = {
        "overall_status": overall,
        "summary": summary,
        "sla_hours": sla_hours,
        "now_utc": now.isoformat(),
        "boundary_ingest": boundary_ingest,
        "boundary_publish": boundary_publish,
        "manifest_run_id": data.get("run_id", "unknown"),
        "manifest_cleaned_records": data.get("cleaned_records"),
    }

    return overall, detail


# ---------------------------------------------------------------------------
# Convenience: đọc và in ra stdout (dùng cho CLI freshness command)
# ---------------------------------------------------------------------------

def freshness_report_lines(status: str, detail: Dict[str, Any]) -> list[str]:
    """Tạo danh sách dòng log có cấu trúc JSON để ghi vào file."""
    import json as _json

    lines = [
        f"freshness_overall={status}",
        f"freshness_summary={detail.get('summary', '')}",
        f"freshness_boundary_ingest={_json.dumps(detail.get('boundary_ingest', {}), ensure_ascii=False)}",
        f"freshness_boundary_publish={_json.dumps(detail.get('boundary_publish', {}), ensure_ascii=False)}",
    ]
    return lines
