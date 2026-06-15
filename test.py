import argparse
import hashlib
import json
import time
from datetime import datetime
from pathlib import Path
from urllib import error, request


DEFAULT_BASE_URL = "http://127.0.0.1:6000"


def safe_cell(data, row, col, default=""):
    try:
        return str(data[row][col]).strip()
    except (IndexError, TypeError):
        return default


def to_float(value):
    try:
        return float(str(value).strip() or 0)
    except (TypeError, ValueError):
        return 0.0


def summarize_response(payload):
    data = payload.get("data", [])
    physical = safe_cell(data, 17, 1, "0")
    online_before = safe_cell(data, 18, 1, "0")
    online_after = safe_cell(data, 19, 1, "0")
    total = to_float(physical) + to_float(online_before) + to_float(online_after)

    return {
        "success": payload.get("success"),
        "valid_range": f"{safe_cell(data, 0, 1)} - {safe_cell(data, 0, 2)}",
        "query_range": f"{safe_cell(data, 1, 1)} - {safe_cell(data, 1, 2)}",
        "row17": data[17] if len(data) > 17 else None,
        "row18": data[18] if len(data) > 18 else None,
        "row19": data[19] if len(data) > 19 else None,
        "physical": physical,
        "online_before": online_before,
        "online_after": online_after,
        "total": round(total, 2),
        "row_count": len(data),
        "data": data,
    }


def data_fingerprint(data):
    raw = json.dumps(data, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def diff_data(first_data, current_data):
    diffs = []
    max_len = max(len(first_data), len(current_data))
    for index in range(max_len):
        first_row = first_data[index] if index < len(first_data) else None
        current_row = current_data[index] if index < len(current_data) else None
        if first_row != current_row:
            diffs.append({
                "row": index,
                "first": first_row,
                "current": current_row,
            })
    return diffs


def diff_summary(first, current, compare_all=True):
    keys = ["success", "valid_range", "query_range", "row_count"]
    diffs = []
    for key in keys:
        if first.get(key) != current.get(key):
            diffs.append({
                "field": key,
                "first": first.get(key),
                "current": current.get(key),
            })
    if not compare_all:
        for key in ["row17", "row18", "row19", "physical", "online_before", "online_after", "total"]:
            if first.get(key) != current.get(key):
                diffs.append({
                    "field": key,
                    "first": first.get(key),
                    "current": current.get(key),
                })
        return diffs

    for row_diff in diff_data(first.get("data", []), current.get("data", [])):
        diffs.append({
            "field": f"data[{row_diff['row']}]",
            "first": row_diff["first"],
            "current": row_diff["current"],
        })
    return diffs


def call_crawler(base_url, endpoint, idno, brdt, timeout):
    url = f"{base_url.rstrip('/')}/{endpoint}"
    body = json.dumps({"idno": idno, "brDt": brdt}).encode("utf-8")
    req = request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    started = time.perf_counter()
    try:
        with request.urlopen(req, timeout=timeout) as response:
            response_body = response.read().decode("utf-8")
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc

    elapsed = time.perf_counter() - started
    return json.loads(response_body), elapsed, url


def default_output_path():
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"test_result_{stamp}.json"


def main():
    parser = argparse.ArgumentParser(
        description="Repeatedly call SecondEdition crawler and compare the full returned data."
    )
    parser.add_argument("--idno", required=True, help="身分證字號")
    parser.add_argument("--brdt", required=True, help="民國生日，例如 099/01/01")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="crawler base URL")
    parser.add_argument("--period", choices=["1", "6"], default="1", help="1=當年積分, 6=六年積分")
    parser.add_argument("--count", type=int, default=5, help="呼叫次數")
    parser.add_argument("--sleep", type=float, default=1.0, help="每次呼叫間隔秒數")
    parser.add_argument("--timeout", type=int, default=180, help="單次 request timeout 秒數")
    parser.add_argument("--summary-only", action="store_true", help="只比對摘要與 17/18/19 列，不比對完整 data")
    parser.add_argument("--output", default=default_output_path(), help="跑完後匯出的 JSON 檔名")
    parser.add_argument("--dump-json", action="store_true", help="保留相容用；現在預設就會印出完整 data")
    args = parser.parse_args()

    endpoint = "run_one_6year" if args.period == "6" else "run_one_1year"
    first_summary = None
    results = []

    print(f"crawler={args.base_url.rstrip('/')}/{endpoint}")
    print(f"count={args.count} sleep={args.sleep}s timeout={args.timeout}s")
    print(f"output={args.output}")
    print()

    for index in range(1, args.count + 1):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"===== Run {index}/{args.count} at {now} =====")
        run_result = {
            "run": index,
            "started_at": now,
            "endpoint": endpoint,
            "url": None,
            "elapsed_seconds": None,
            "payload": None,
            "summary": None,
            "diff_from_first": None,
            "error": None,
        }
        try:
            payload, elapsed, url = call_crawler(
                args.base_url,
                endpoint,
                args.idno,
                args.brdt,
                args.timeout,
            )
            summary = summarize_response(payload)
            run_result["url"] = url
            run_result["elapsed_seconds"] = round(elapsed, 3)
            run_result["payload"] = payload
            run_result["summary"] = summary

            print(f"url: {url}")
            print(f"elapsed: {elapsed:.2f}s")
            print(f"success: {summary['success']}")
            print(f"valid_range: {summary['valid_range']}")
            print(f"query_range: {summary['query_range']}")
            print(f"row_count: {summary['row_count']}")
            print("full_data:")
            print(json.dumps(summary["data"], ensure_ascii=False, indent=2))
            print(
                "total(row17+row18+row19): "
                f"{summary['physical']} + {summary['online_before']} + {summary['online_after']} = {summary['total']}"
            )
            print(f"data_sha256_16: {data_fingerprint(summary['data'])}")

            if first_summary is None:
                first_summary = summary
                print("diff_from_first: baseline")
                run_result["diff_from_first"] = "baseline"
            else:
                diffs = diff_summary(first_summary, summary, compare_all=not args.summary_only)
                run_result["diff_from_first"] = diffs
                if not diffs:
                    print("diff_from_first: no difference")
                else:
                    print(f"diff_from_first: {len(diffs)} difference(s)")
                    for diff in diffs:
                        print(f"  - {diff['field']}: first={diff['first']} current={diff['current']}")

        except Exception as exc:
            run_result["error"] = str(exc)
            print(f"ERROR: {exc}")

        results.append(run_result)

        print()
        if index < args.count:
            time.sleep(args.sleep)

    output = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "base_url": args.base_url.rstrip("/"),
        "endpoint": endpoint,
        "idno": args.idno,
        "brdt": args.brdt,
        "count": args.count,
        "sleep": args.sleep,
        "timeout": args.timeout,
        "summary_only": args.summary_only,
        "results": results,
    }
    output_path = Path(args.output)
    output_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"exported_json: {output_path.resolve()}")


if __name__ == "__main__":
    main()
