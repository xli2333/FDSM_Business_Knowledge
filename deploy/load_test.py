from __future__ import annotations

import argparse
import json
import statistics
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed


def request_once(url: str, timeout: float) -> dict:
    started_at = time.perf_counter()
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            response.read(1024)
            status = response.status
            ok = 200 <= status < 400
            error = None
    except urllib.error.HTTPError as exc:
        status = exc.code
        ok = 200 <= status < 400
        error = None if ok else str(exc)
    except Exception as exc:
        status = 0
        ok = False
        error = str(exc)
    return {
        "url": url,
        "status": status,
        "ok": ok,
        "error": error,
        "latency_ms": int((time.perf_counter() - started_at) * 1000),
    }


def parse_status_codes(raw_value: str) -> set[int]:
    codes: set[int] = set()
    for item in str(raw_value or "").split(","):
        cleaned = item.strip()
        if not cleaned:
            continue
        codes.add(int(cleaned))
    return codes


def is_acceptable_result(item: dict, accepted_statuses: set[int]) -> bool:
    if item["ok"]:
        return True
    if item["status"] in accepted_statuses:
        return True
    return item["url"].endswith("/api/auth/cas/login?redirect=/admin") and item["status"] == 503


def percentile(values: list[int], percent: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(round((percent / 100) * (len(ordered) - 1))))
    return ordered[index]


def main() -> None:
    parser = argparse.ArgumentParser(description="Lightweight HTTP load test for the FDSM Docker deployment.")
    parser.add_argument("--base-url", default="http://127.0.0.1:18080")
    parser.add_argument("--requests", type=int, default=120)
    parser.add_argument("--concurrency", type=int, default=24)
    parser.add_argument("--timeout", type=float, default=10)
    parser.add_argument(
        "--accepted-statuses",
        default="429",
        help="Comma-separated non-2xx statuses treated as expected protection responses during load tests.",
    )
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    urls = [
        f"{base_url}/healthz",
        f"{base_url}/api/health",
        f"{base_url}/api/home/feed?language=zh",
        f"{base_url}/api/auth/cas/login?redirect=/admin",
    ]
    expanded_urls = [urls[index % len(urls)] for index in range(args.requests)]
    started_at = time.perf_counter()
    results = []
    with ThreadPoolExecutor(max_workers=max(1, args.concurrency)) as pool:
        futures = [pool.submit(request_once, url, args.timeout) for url in expanded_urls]
        for future in as_completed(futures):
            results.append(future.result())

    accepted_statuses = parse_status_codes(args.accepted_statuses)
    latencies = [item["latency_ms"] for item in results]
    failures = [item for item in results if not is_acceptable_result(item, accepted_statuses)]
    accepted_non_2xx = [item for item in results if not item["ok"] and is_acceptable_result(item, accepted_statuses)]
    by_status: dict[str, int] = {}
    for item in results:
        key = str(item["status"])
        by_status[key] = by_status.get(key, 0) + 1

    payload = {
        "base_url": base_url,
        "requests": args.requests,
        "concurrency": args.concurrency,
        "elapsed_ms": int((time.perf_counter() - started_at) * 1000),
        "success_count": len(results) - len(failures),
        "failure_count": len(failures),
        "accepted_non_2xx_count": len(accepted_non_2xx),
        "accepted_statuses": sorted(accepted_statuses),
        "status_counts": by_status,
        "latency_ms": {
            "min": min(latencies) if latencies else 0,
            "median": int(statistics.median(latencies)) if latencies else 0,
            "p95": percentile(latencies, 95),
            "max": max(latencies) if latencies else 0,
        },
        "failures": failures[:10],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
