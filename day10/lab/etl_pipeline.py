#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Lab Day 10 — ETL entrypoint: ingest → clean → validate → embed → log.

Tiếp nối Day 09: cùng corpus docs trong data/docs/; pipeline này xử lý *export* raw (CSV)
đại diện cho lớp ingestion từ DB/API trước khi embed lại vector store.

Chạy nhanh:
  pip install -r requirements.txt
  cp .env.example .env
  python etl_pipeline.py run

Chế độ inject (Sprint 3 — bỏ fix refund để expectation fail / eval xấu):
  python etl_pipeline.py run --run-id inject-bad --no-refund-fix --skip-validate

Kiểm tra freshness:
  python etl_pipeline.py freshness --manifest artifacts/manifests/manifest_<run-id>.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# Fix Windows cp1252 encoding issue — reconfigure stdout/stderr sang UTF-8
import sys as _sys
if hasattr(_sys.stdout, "reconfigure"):
    _sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(_sys.stderr, "reconfigure"):
    _sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from dotenv import load_dotenv

from monitoring.freshness_check import check_manifest_freshness, freshness_report_lines
from quality.expectations import run_expectations
from transform.cleaning_rules import (
    clean_rows,
    load_raw_csv,
    write_cleaned_csv,
    write_quarantine_csv,
)

load_dotenv()

ROOT = Path(__file__).resolve().parent
RAW_DEFAULT = ROOT / "data" / "raw" / "policy_export_dirty.csv"
ART = ROOT / "artifacts"
LOG_DIR = ART / "logs"
MAN_DIR = ART / "manifests"
QUAR_DIR = ART / "quarantine"
CLEAN_DIR = ART / "cleaned"


# ---------------------------------------------------------------------------
# Structured logging helpers
# ---------------------------------------------------------------------------

def _ensure_dirs() -> None:
    for p in (LOG_DIR, MAN_DIR, QUAR_DIR, CLEAN_DIR):
        p.mkdir(parents=True, exist_ok=True)


def _append_log(path: Path, line: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def _make_logger(log_path: Path):
    """Trả về hàm log(msg) vừa in ra stdout vừa ghi vào file."""
    def log(msg: str) -> None:
        print(msg)
        _append_log(log_path, msg)
    return log


# ---------------------------------------------------------------------------
# Subcommand: run
# ---------------------------------------------------------------------------

def cmd_run(args: argparse.Namespace) -> int:
    run_id = args.run_id or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%MZ")
    raw_path = Path(args.raw)

    if not raw_path.is_file():
        print(f"ERROR: raw file not found: {raw_path}", file=sys.stderr)
        return 1

    _ensure_dirs()
    safe_run_id = run_id.replace(":", "-")
    log_path = LOG_DIR / f"run_{safe_run_id}.log"
    log = _make_logger(log_path)

    # ── Ingest ────────────────────────────────────────────────────────────────
    ingest_time_utc = datetime.now(timezone.utc).isoformat()
    rows = load_raw_csv(raw_path)
    raw_count = len(rows)

    # Structured log đầu run — JSON-friendly fields
    log(json.dumps({
        "event": "pipeline_start",
        "run_id": run_id,
        "raw_path": str(raw_path.relative_to(ROOT)),
        "raw_records": raw_count,
        "ingest_time_utc": ingest_time_utc,
    }, ensure_ascii=False))

    # Shorthand log (khớp với grading check pattern)
    log(f"run_id={run_id}")
    log(f"raw_records={raw_count}")

    # ── Clean ─────────────────────────────────────────────────────────────────
    cleaned, quarantine = clean_rows(
        rows,
        apply_refund_window_fix=not args.no_refund_fix,
    )

    cleaned_path = CLEAN_DIR / f"cleaned_{safe_run_id}.csv"
    quar_path = QUAR_DIR / f"quarantine_{safe_run_id}.csv"
    write_cleaned_csv(cleaned_path, cleaned)
    write_quarantine_csv(quar_path, quarantine)

    log(f"cleaned_records={len(cleaned)}")
    log(f"quarantine_records={len(quarantine)}")
    log(f"cleaned_csv={cleaned_path.relative_to(ROOT)}")
    log(f"quarantine_csv={quar_path.relative_to(ROOT)}")

    # Log breakdown quarantine theo reason
    quar_by_reason: Dict[str, int] = {}
    for r in quarantine:
        reason = r.get("reason", "unknown")
        quar_by_reason[reason] = quar_by_reason.get(reason, 0) + 1
    log(json.dumps({"event": "quarantine_breakdown", **quar_by_reason}, ensure_ascii=False))

    # ── Validate (Expectation Suite) ──────────────────────────────────────────
    results, halt = run_expectations(cleaned)
    for r in results:
        sym = "OK" if r.passed else "FAIL"
        detail_str = r.detail
        if r.violations:
            # Log tối đa 3 violation đầu để tránh log quá dài
            detail_str += f" | violations_sample={r.violations[:3]}"
        log(f"expectation[{r.name}] {sym} ({r.severity}) :: {detail_str}")

    if halt and not args.skip_validate:
        log(json.dumps({
            "event": "PIPELINE_HALT",
            "reason": "expectation_suite_failed",
            "failed": [r.name for r in results if not r.passed and r.severity == "halt"],
        }, ensure_ascii=False))
        log("PIPELINE_HALT: expectation suite failed (halt).")
        return 2

    if halt and args.skip_validate:
        log("WARN: expectation failed but --skip-validate → tiếp tục embed (chỉ dùng cho demo Sprint 3).")

    # ── Embed (ChromaDB) ──────────────────────────────────────────────────────
    embed_ok, publish_time_utc = _cmd_embed_internal(
        cleaned_path,
        run_id=run_id,
        log=log,
    )
    if not embed_ok:
        return 3

    # ── Manifest ──────────────────────────────────────────────────────────────
    latest_exported = max(
        (r.get("exported_at") or "" for r in cleaned),
        default="",
    )

    manifest: Dict[str, Any] = {
        "run_id": run_id,
        "run_timestamp": publish_time_utc,          # Boundary 2: PUBLISH time
        "ingest_time_utc": ingest_time_utc,         # Boundary 1: INGEST time (thêm mới)
        "raw_path": str(raw_path.relative_to(ROOT)),
        "raw_records": raw_count,
        "cleaned_records": len(cleaned),
        "quarantine_records": len(quarantine),
        "quarantine_breakdown": quar_by_reason,
        "latest_exported_at": latest_exported,      # max exported_at của cleaned rows
        "no_refund_fix": bool(args.no_refund_fix),
        "skipped_validate": bool(args.skip_validate and halt),
        "cleaned_csv": str(cleaned_path.relative_to(ROOT)),
        "chroma_path": os.environ.get("CHROMA_DB_PATH", "./chroma_db"),
        "chroma_collection": os.environ.get("CHROMA_COLLECTION", "day10_kb"),
        "expectations": [
            {"name": r.name, "passed": r.passed, "severity": r.severity, "detail": r.detail}
            for r in results
        ],
    }

    man_path = MAN_DIR / f"manifest_{safe_run_id}.json"
    man_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"manifest_written={man_path.relative_to(ROOT)}")

    # ── Freshness check (2 boundary) ─────────────────────────────────────────
    sla_hours = float(os.environ.get("FRESHNESS_SLA_HOURS", "24"))
    status, fdetail = check_manifest_freshness(man_path, sla_hours=sla_hours)
    for fline in freshness_report_lines(status, fdetail):
        log(fline)

    # ── Kết thúc ─────────────────────────────────────────────────────────────
    log(json.dumps({
        "event": "PIPELINE_OK",
        "run_id": run_id,
        "cleaned_records": len(cleaned),
        "quarantine_records": len(quarantine),
        "embed_count": len(cleaned),
        "freshness_status": status,
    }, ensure_ascii=False))
    log("PIPELINE_OK")
    return 0


# ---------------------------------------------------------------------------
# Embed internal
# ---------------------------------------------------------------------------

def _cmd_embed_internal(
    cleaned_csv: Path,
    *,
    run_id: str,
    log,
) -> tuple[bool, str]:
    """
    Embed cleaned CSV vào ChromaDB.

    Returns (success, publish_time_utc).
    Idempotent: upsert theo chunk_id + prune id lạc hậu.
    """
    try:
        import chromadb
        from chromadb.utils import embedding_functions
    except ImportError:
        log("ERROR: chromadb chưa cài. pip install -r requirements.txt")
        return False, ""

    db_path = os.environ.get("CHROMA_DB_PATH", str(ROOT / "chroma_db"))
    collection_name = os.environ.get("CHROMA_COLLECTION", "day10_kb")
    model_name = os.environ.get("EMBEDDING_MODEL", "all-MiniLM-L6-v2")

    rows = load_raw_csv(cleaned_csv)
    if not rows:
        log("WARN: cleaned CSV rỗng — không embed.")
        return True, datetime.now(timezone.utc).isoformat()

    client = chromadb.PersistentClient(path=db_path)
    emb = embedding_functions.SentenceTransformerEmbeddingFunction(model_name=model_name)
    col = client.get_or_create_collection(name=collection_name, embedding_function=emb)

    ids = [r["chunk_id"] for r in rows]

    # Prune: xoá id cũ không còn trong lần run này → index = snapshot publish
    try:
        prev = col.get(include=[])
        prev_ids = set(prev.get("ids") or [])
        drop = sorted(prev_ids - set(ids))
        if drop:
            col.delete(ids=drop)
            log(f"embed_prune_removed={len(drop)} ids={drop[:5]}")
        else:
            log("embed_prune_removed=0")
    except Exception as exc:
        log(f"WARN: embed prune skip: {exc}")

    documents = [r["chunk_text"] for r in rows]
    metadatas = [
        {
            "doc_id": r.get("doc_id", ""),
            "effective_date": r.get("effective_date", ""),
            "exported_at": r.get("exported_at", ""),
            "run_id": run_id,
        }
        for r in rows
    ]

    # Upsert theo chunk_id (idempotent — chạy lại không phình collection)
    col.upsert(ids=ids, documents=documents, metadatas=metadatas)
    publish_time_utc = datetime.now(timezone.utc).isoformat()
    log(f"embed_upsert count={len(ids)} collection={collection_name}")
    log(f"embed_publish_time_utc={publish_time_utc}")

    return True, publish_time_utc


# ---------------------------------------------------------------------------
# Subcommand: freshness
# ---------------------------------------------------------------------------

def cmd_freshness(args: argparse.Namespace) -> int:
    p = Path(args.manifest)
    if not p.is_file():
        print(f"manifest not found: {p}", file=sys.stderr)
        return 1
    sla = float(os.environ.get("FRESHNESS_SLA_HOURS", "24"))
    status, detail = check_manifest_freshness(p, sla_hours=sla)
    print(status)
    for line in freshness_report_lines(status, detail):
        print(line)
    print(json.dumps(detail, ensure_ascii=False, indent=2))
    return 0 if status != "FAIL" else 1


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="Day 10 ETL pipeline")
    sub = parser.add_subparsers(dest="command", required=True)

    # ── run ──────────────────────────────────────────────────────────────────
    p_run = sub.add_parser("run", help="ingest → clean → validate → embed")
    p_run.add_argument(
        "--raw",
        default=str(RAW_DEFAULT),
        help="Đường dẫn CSV raw export",
    )
    p_run.add_argument("--run-id", default="", help="ID run (mặc định: UTC timestamp)")
    p_run.add_argument(
        "--no-refund-fix",
        action="store_true",
        help="Không áp dụng rule fix cửa sổ 14→7 ngày (dùng cho inject corruption / before).",
    )
    p_run.add_argument(
        "--skip-validate",
        action="store_true",
        help="Vẫn embed khi expectation halt (chỉ phục vụ demo Sprint 3).",
    )
    p_run.set_defaults(func=cmd_run)

    # ── freshness ─────────────────────────────────────────────────────────────
    p_fr = sub.add_parser("freshness", help="Đọc manifest và kiểm tra SLA freshness (2 boundary)")
    p_fr.add_argument("--manifest", required=True, help="Đường dẫn manifest JSON")
    p_fr.set_defaults(func=cmd_freshness)

    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
