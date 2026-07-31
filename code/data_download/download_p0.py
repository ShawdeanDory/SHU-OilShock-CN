"""Download public P0 source snapshots with reproducibility metadata."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = Path(__file__).with_name("p0_sources.json")
RAW_DIR = REPO_ROOT / "data" / "raw"
META_DIR = RAW_DIR / "_meta"
MANIFEST_CSV = RAW_DIR / "source_manifest.csv"
MANIFEST_JSON = RAW_DIR / "source_manifest.json"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/138.0.0.0 Safari/537.36"
)
MANIFEST_FIELDS = [
    "artifact_id",
    "source_id",
    "status",
    "required",
    "url",
    "local_path",
    "downloaded_at",
    "checked_at",
    "http_status",
    "content_type",
    "content_length_header",
    "size_bytes",
    "sha256",
    "etag",
    "last_modified",
    "error",
]


@dataclass(frozen=True)
class Source:
    artifact_id: str
    source_id: str
    url: str
    filename_template: str
    format: str
    min_bytes: int
    required: bool
    expected_csv_columns: tuple[str, ...] = ()
    requires_env: str | None = None
    referer: str | None = None
    user_agent: str | None = None
    local_snapshot: bool = False


def now_shanghai() -> datetime:
    return datetime.now(ZoneInfo("Asia/Shanghai"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_sources() -> tuple[dict[str, Any], list[Source]]:
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    sources = []
    for item in config["sources"]:
        sources.append(
            Source(
                artifact_id=item["artifact_id"],
                source_id=item["source_id"],
                url=item["url"],
                filename_template=item["filename_template"],
                format=item["format"],
                min_bytes=int(item.get("min_bytes", 1)),
                required=bool(item.get("required", False)),
                expected_csv_columns=tuple(item.get("expected_csv_columns", [])),
                requires_env=item.get("requires_env"),
                referer=item.get("referer"),
                user_agent=item.get("user_agent"),
                local_snapshot=bool(item.get("local_snapshot", False)),
            )
        )
    return config, sources


def make_session() -> requests.Session:
    retry = Retry(
        total=2,
        connect=2,
        read=0,
        backoff_factor=1.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET",),
        respect_retry_after_header=True,
    )
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT, "Accept": "*/*"})
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.mount("http://", HTTPAdapter(max_retries=retry))
    return session


def parse_curl_headers(path: Path) -> dict[str, str]:
    """Return headers from the final response block written by curl."""
    if not path.exists():
        return {}
    blocks = path.read_text(encoding="iso-8859-1").replace("\r\n", "\n").split("\n\n")
    header_lines = next(
        (block.splitlines() for block in reversed(blocks) if block.startswith("HTTP/")),
        [],
    )
    headers: dict[str, str] = {}
    for line in header_lines[1:]:
        if ":" in line:
            key, value = line.split(":", 1)
            headers[key.strip().lower()] = value.strip()
    return headers


def download_with_curl(source: Source, partial: Path) -> dict[str, Any]:
    """Use system curl when available; it is more reliable on this Windows host."""
    curl = shutil.which("curl.exe") or shutil.which("curl")
    if not curl:
        raise FileNotFoundError("curl executable not found")
    header_path = partial.with_suffix(partial.suffix + ".headers")
    if header_path.exists():
        header_path.unlink()
    command = [
        curl,
        "--location",
        "--fail",
        "--silent",
        "--show-error",
        "--connect-timeout",
        "12",
        "--max-time",
        "120",
        "--retry",
        "3",
        "--retry-delay",
        "2",
        "--retry-all-errors",
        "--dump-header",
        str(header_path),
        "--output",
        str(partial),
        "--write-out",
        "%{http_code}\\t%{content_type}\\t%{size_download}\\t%{url_effective}",
    ]
    if source.referer:
        command.extend(["--referer", source.referer])
    if source.user_agent:
        command.extend(["--user-agent", source.user_agent])
    command.append(source.url)
    try:
        completed = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            timeout=140,
        )
        parts = completed.stdout.strip().split("\t", 3)
        headers = parse_curl_headers(header_path)
        return {
            "http_status": parts[0] if parts else "",
            "content_type": parts[1] if len(parts) > 1 else headers.get("content-type", ""),
            "content_length_header": headers.get("content-length", ""),
            "etag": headers.get("etag", ""),
            "last_modified": headers.get("last-modified", ""),
        }
    finally:
        if header_path.exists():
            header_path.unlink()


def download_with_requests(
    session: requests.Session,
    source: Source,
    partial: Path,
) -> dict[str, Any]:
    headers = {}
    if source.referer:
        headers["Referer"] = source.referer
    if source.user_agent:
        headers["User-Agent"] = source.user_agent
    with session.get(
        source.url,
        headers=headers,
        timeout=(15, 60),
        stream=True,
    ) as response:
        metadata = {
            "http_status": response.status_code,
            "content_type": response.headers.get("Content-Type", ""),
            "content_length_header": response.headers.get("Content-Length", ""),
            "etag": response.headers.get("ETag", ""),
            "last_modified": response.headers.get("Last-Modified", ""),
        }
        response.raise_for_status()
        with partial.open("wb") as handle:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    handle.write(chunk)
    return metadata


def read_manifest() -> dict[str, dict[str, Any]]:
    if not MANIFEST_JSON.exists():
        return {}
    rows = json.loads(MANIFEST_JSON.read_text(encoding="utf-8"))
    return {row["artifact_id"]: row for row in rows}


def write_manifest(rows_by_id: dict[str, dict[str, Any]]) -> None:
    rows: list[dict[str, Any]] = []
    for key in sorted(rows_by_id):
        row = dict(rows_by_id[key])
        if row.get("status") in {"DOWNLOADED", "CACHED"}:
            local_path = row.get("local_path", "")
            if not local_path or not (REPO_ROOT / local_path).exists():
                row.update(
                    {
                        "status": "REMOTE_ONLY",
                        "local_path": "",
                        "size_bytes": "",
                        "sha256": "",
                        "error": "manifest local snapshot is absent; rerun download or provide a browser-extracted snapshot before marking CACHED",
                    }
                )
        rows.append(row)
    with MANIFEST_JSON.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(rows, ensure_ascii=False, indent=2) + "\n")
    with MANIFEST_CSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=MANIFEST_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows({key: row.get(key, "") for key in MANIFEST_FIELDS} for row in rows)


def validate_csv_header(path: Path, expected: tuple[str, ...]) -> None:
    if not expected:
        return
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        header = next(csv.reader(handle))
    missing = [column for column in expected if column not in header]
    if missing:
        raise ValueError(f"CSV missing expected columns: {missing}; actual={header[:20]}")


def cached_record(source: Source, target: Path, timestamp: str) -> dict[str, Any]:
    download_date = target.stem.rsplit("_", 1)[-1]
    meta_path = META_DIR / f"{source.artifact_id}_{download_date}.json"
    existing: dict[str, Any] = {}
    if meta_path.exists():
        existing = json.loads(meta_path.read_text(encoding="utf-8"))
    return {
        "artifact_id": source.artifact_id,
        "source_id": source.source_id,
        "status": "CACHED",
        "required": source.required,
        "url": source.url,
        "local_path": target.relative_to(REPO_ROOT).as_posix(),
        "downloaded_at": existing.get("downloaded_at", timestamp),
        "checked_at": timestamp,
        "http_status": existing.get("http_status", ""),
        "content_type": existing.get("content_type", ""),
        "content_length_header": existing.get("content_length_header", ""),
        "size_bytes": target.stat().st_size,
        "sha256": sha256_file(target),
        "etag": existing.get("etag", ""),
        "last_modified": existing.get("last_modified", ""),
        "error": "",
    }


def download_one(
    session: requests.Session,
    source: Source,
    *,
    refresh: bool,
    download_date: str,
    timestamp: str,
) -> dict[str, Any]:
    filename = source.filename_template.format(download_date=download_date)
    target = RAW_DIR / filename
    if not target.exists() and not refresh and "{download_date}" in source.filename_template:
        pattern = source.filename_template.replace("{download_date}", "*")
        prior_snapshots = sorted(RAW_DIR.glob(pattern))
        if prior_snapshots:
            target = prior_snapshots[-1]
    partial = target.with_suffix(target.suffix + ".part")

    if source.requires_env and not os.getenv(source.requires_env):
        return {
            "artifact_id": source.artifact_id,
            "source_id": source.source_id,
            "status": "SKIPPED_MISSING_ENV",
            "required": source.required,
            "url": source.url,
            "local_path": "",
            "downloaded_at": timestamp,
            "checked_at": timestamp,
            "error": f"missing environment variable {source.requires_env}",
        }

    if source.local_snapshot:
        if not target.exists():
            return {
                "artifact_id": source.artifact_id,
                "source_id": source.source_id,
                "status": "ERROR",
                "required": source.required,
                "url": source.url,
                "local_path": "",
                "downloaded_at": timestamp,
                "checked_at": timestamp,
                "error": (
                    "versioned browser-extracted snapshot is missing; "
                    f"expected {target.relative_to(REPO_ROOT).as_posix()}"
                ),
            }
        validate_csv_header(target, source.expected_csv_columns)
        record = cached_record(source, target, timestamp)
        record.update(
            {
                "http_status": "200-browser",
                "content_type": "text/csv; charset=utf-8",
            }
        )
        meta_path = META_DIR / f"{source.artifact_id}_{download_date}.json"
        meta_path.write_text(
            json.dumps(record, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return record

    if target.exists() and not refresh:
        validate_csv_header(target, source.expected_csv_columns)
        return cached_record(source, target, timestamp)

    if partial.exists():
        partial.unlink()

    record: dict[str, Any] = {
        "artifact_id": source.artifact_id,
        "source_id": source.source_id,
        "status": "ERROR",
        "required": source.required,
        "url": source.url,
        "local_path": "",
        "downloaded_at": timestamp,
        "checked_at": timestamp,
        "http_status": "",
        "content_type": "",
        "content_length_header": "",
        "size_bytes": "",
        "sha256": "",
        "etag": "",
        "last_modified": "",
        "error": "",
    }
    try:
        if shutil.which("curl.exe") or shutil.which("curl"):
            response_metadata = download_with_curl(source, partial)
        else:
            response_metadata = download_with_requests(session, source, partial)
        record.update(response_metadata)

        size = partial.stat().st_size
        if size < source.min_bytes:
            raise ValueError(f"downloaded file is too small: {size} < {source.min_bytes}")
        validate_csv_header(partial, source.expected_csv_columns)
        partial.replace(target)

        record.update(
            {
                "status": "DOWNLOADED",
                "local_path": target.relative_to(REPO_ROOT).as_posix(),
                "size_bytes": size,
                "sha256": sha256_file(target),
                "error": "",
            }
        )
        meta_path = META_DIR / f"{source.artifact_id}_{download_date}.json"
        meta_path.write_text(
            json.dumps(record, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except Exception as exc:
        if partial.exists():
            partial.unlink()
        record["error"] = f"{type(exc).__name__}: {exc}"
    return record


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        action="append",
        default=[],
        help="Download only this artifact_id; may be specified multiple times.",
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Replace today's existing snapshot. Without this flag raw files are never overwritten.",
    )
    parser.add_argument("--list", action="store_true", help="List configured sources and exit.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config, sources = load_sources()
    if args.list:
        for source in sources:
            print(
                f"{source.artifact_id}\trequired={str(source.required).lower()}"
                f"\t{source.source_id}\t{source.url}"
            )
        return 0

    selected_ids = set(args.source)
    if selected_ids:
        unknown = selected_ids - {source.artifact_id for source in sources}
        if unknown:
            print(f"Unknown artifact_id(s): {sorted(unknown)}", file=sys.stderr)
            return 2
        sources = [source for source in sources if source.artifact_id in selected_ids]

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    META_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = now_shanghai().isoformat(timespec="seconds")
    download_date = now_shanghai().strftime("%Y%m%d")
    manifest = read_manifest()
    session = make_session()

    required_failures = 0
    for source in sources:
        print(f"[DOWNLOAD] {source.artifact_id}", flush=True)
        record = download_one(
            session,
            source,
            refresh=args.refresh,
            download_date=download_date,
            timestamp=timestamp,
        )
        manifest[source.artifact_id] = record
        print(
            f"[{record['status']}] {source.artifact_id}"
            f" bytes={record.get('size_bytes', '')}"
            f" error={record.get('error', '')}",
            flush=True,
        )
        if source.required and record["status"] not in {"DOWNLOADED", "CACHED"}:
            required_failures += 1

    write_manifest(manifest)
    summary = {
        "schema_version": config["schema_version"],
        "cutoff_date": config["cutoff_date"],
        "selected": len(sources),
        "required_failures": required_failures,
        "manifest": MANIFEST_CSV.relative_to(REPO_ROOT).as_posix(),
    }
    print(json.dumps(summary, ensure_ascii=False))
    return 1 if required_failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
