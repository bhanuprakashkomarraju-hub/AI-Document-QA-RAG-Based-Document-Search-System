from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib import request


BASE_URL = "http://127.0.0.1:8000"
DOCS_FOLDER = Path(r"C:\Users\Archana\Desktop\project\PDF Extraction rag model\test")
QUESTIONS_FILE = DOCS_FOLDER / "questions.txt"
RESULTS_DIR = DOCS_FOLDER / "results"


def http_get_json(url: str, timeout: int = 60) -> dict[str, Any]:
    with request.urlopen(url, timeout=timeout) as resp:  # noqa: S310 - local service
        return json.loads(resp.read().decode("utf-8"))


def http_post_json(url: str, payload: dict[str, Any], timeout: int = 30) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    req = request.Request(
        url=url,
        data=body,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    with request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - local service
        return json.loads(resp.read().decode("utf-8"))


def upload_pdf(pdf_path: Path) -> dict[str, Any]:
    cmd = [
        "curl.exe",
        "-s",
        "-X",
        "POST",
        f"{BASE_URL}/upload",
        "-F",
        f"file=@{pdf_path};type=application/pdf",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or f"curl failed: {proc.returncode}")
    return json.loads(proc.stdout)


def ensure_dirs() -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)


def load_questions() -> list[str]:
    if QUESTIONS_FILE.exists():
        lines = [line.strip() for line in QUESTIONS_FILE.read_text(encoding="utf-8").splitlines()]
        lines = [line for line in lines if line]
        if lines:
            return lines
    return [
        "What is the main topic of this document?",
        "Summarize key points from the document.",
        "What dates are mentioned?",
        "What is the CEO birthday?",
    ]


def safe_num(value: Any) -> float:
    try:
        return float(value)
    except Exception:  # noqa: BLE001
        return 0.0


def build_report(prev_file: Path | None, curr_file: Path, report_file: Path) -> None:
    lines: list[str] = []
    lines.append("# RAG Test Comparison Report")
    lines.append("")
    lines.append(f"- Generated: {datetime.now().isoformat()}")
    lines.append(f"- Current run: `{curr_file}`")
    lines.append("")

    if prev_file is None:
        lines.append("Only one run available. Need at least two runs for comparison.")
        report_file.write_text("\n".join(lines), encoding="utf-8")
        return

    prev = json.loads(prev_file.read_text(encoding="utf-8"))
    curr = json.loads(curr_file.read_text(encoding="utf-8"))

    prev_summary = prev.get("summary", {})
    curr_summary = curr.get("summary", {})

    prev_avg = safe_num(prev_summary.get("avg_response_ms"))
    curr_avg = safe_num(curr_summary.get("avg_response_ms"))

    prev_us = safe_num(prev_summary.get("upload_success"))
    curr_us = safe_num(curr_summary.get("upload_success"))
    prev_uf = safe_num(prev_summary.get("upload_fail"))
    curr_uf = safe_num(curr_summary.get("upload_fail"))
    prev_qs = safe_num(prev_summary.get("query_success"))
    curr_qs = safe_num(curr_summary.get("query_success"))
    prev_qf = safe_num(prev_summary.get("query_fail"))
    curr_qf = safe_num(curr_summary.get("query_fail"))
    prev_nf = safe_num(prev_summary.get("not_found_count"))
    curr_nf = safe_num(curr_summary.get("not_found_count"))

    lines.append("## Files Compared")
    lines.append(f"- Previous: `{prev_file}`")
    lines.append(f"- Current: `{curr_file}`")
    lines.append("")
    lines.append("## Metrics")
    lines.append("| Metric | Previous | Current | Delta |")
    lines.append("|---|---:|---:|---:|")
    lines.append(f"| Upload success | {prev_us:.0f} | {curr_us:.0f} | {(curr_us - prev_us):+.0f} |")
    lines.append(f"| Upload fail | {prev_uf:.0f} | {curr_uf:.0f} | {(curr_uf - prev_uf):+.0f} |")
    lines.append(f"| Query success | {prev_qs:.0f} | {curr_qs:.0f} | {(curr_qs - prev_qs):+.0f} |")
    lines.append(f"| Query fail | {prev_qf:.0f} | {curr_qf:.0f} | {(curr_qf - prev_qf):+.0f} |")
    lines.append(f"| Not found count | {prev_nf:.0f} | {curr_nf:.0f} | {(curr_nf - prev_nf):+.0f} |")
    lines.append(f"| Avg response (ms) | {prev_avg:.2f} | {curr_avg:.2f} | {(curr_avg - prev_avg):+.2f} |")
    lines.append("")
    lines.append("## Interpretation")
    if curr_qf < prev_qf:
        lines.append("- Reliability improved (fewer query failures).")
    elif curr_qf > prev_qf:
        lines.append("- Reliability worsened (more query failures).")
    else:
        lines.append("- Reliability unchanged.")

    if curr_avg < prev_avg:
        lines.append("- Latency improved (lower average response time).")
    elif curr_avg > prev_avg:
        lines.append("- Latency worsened (higher average response time).")
    else:
        lines.append("- Latency unchanged.")

    report_file.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    print("[0] Health check...")
    try:
        health = http_get_json(f"{BASE_URL}/health")
        print("Server OK:", health)
    except Exception as exc:  # noqa: BLE001
        print("Server not reachable. Start uvicorn first.", exc)
        return 1

    if not DOCS_FOLDER.exists():
        print(f"Docs folder missing: {DOCS_FOLDER}")
        return 1

    pdfs = sorted(DOCS_FOLDER.glob("*.pdf"))
    if not pdfs:
        print(f"No PDFs found in {DOCS_FOLDER}")
        return 1

    ensure_dirs()
    questions = load_questions()
    stamp = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
    run_file = RESULTS_DIR / f"test_results_{stamp}.json"
    history_file = RESULTS_DIR / "history.jsonl"
    report_file = RESULTS_DIR / "comparison_report.md"

    run: dict[str, Any] = {
        "run_timestamp": datetime.now().isoformat(),
        "base_url": BASE_URL,
        "docs_folder": str(DOCS_FOLDER),
        "questions_file": str(QUESTIONS_FILE),
        "uploads": [],
        "queries": [],
        "summary": {
            "upload_success": 0,
            "upload_fail": 0,
            "query_success": 0,
            "query_fail": 0,
            "not_found_count": 0,
            "avg_response_ms": 0.0,
        },
    }

    print("\n[1] Uploading PDFs...")
    for pdf in pdfs:
        print(f"Uploading: {pdf.name}")
        item = {"file": str(pdf), "status": "failed", "response": None, "error": None}
        try:
            response = upload_pdf(pdf)
            item["response"] = response
            if response.get("status") == "success":
                item["status"] = "success"
                run["summary"]["upload_success"] += 1
                print(f"  -> success, chunks: {response.get('chunks_created')}")
            else:
                run["summary"]["upload_fail"] += 1
                print(f"  -> failed response: {response}")
        except Exception as exc:  # noqa: BLE001
            item["error"] = str(exc)
            run["summary"]["upload_fail"] += 1
            print(f"  -> upload error: {exc}")
        run["uploads"].append(item)

    print("\n[2] Running questions...")
    for idx, question in enumerate(questions, start=1):
        print(f"\nQ{idx}: {question}")
        query_item: dict[str, Any] = {
            "question_index": idx,
            "question": question,
            "status": "failed",
            "answer": None,
            "response_time_ms": None,
            "retrieved_count": 0,
            "top_source": None,
            "top_score": None,
            "error": None,
        }
        try:
            result = http_post_json(f"{BASE_URL}/query", {"question": question})
            query_item["status"] = "success"
            query_item["answer"] = result.get("answer")
            query_item["response_time_ms"] = result.get("response_time_ms")
            chunks = result.get("retrieved_chunks", [])
            query_item["retrieved_count"] = len(chunks)
            run["summary"]["query_success"] += 1

            if query_item["answer"] == "Not found":
                run["summary"]["not_found_count"] += 1

            if chunks:
                top = chunks[0]
                query_item["top_source"] = top.get("source")
                query_item["top_score"] = top.get("rerank_score", top.get("score"))

            print(f"Answer: {query_item['answer']}")
            print(
                f"Time(ms): {query_item['response_time_ms']} | "
                f"Retrieved: {query_item['retrieved_count']}"
            )
        except Exception as exc:  # noqa: BLE001
            query_item["error"] = str(exc)
            run["summary"]["query_fail"] += 1
            print(f"Query failed: {exc}")

        run["queries"].append(query_item)

    success_queries = [q for q in run["queries"] if q["status"] == "success" and q["response_time_ms"] is not None]
    if success_queries:
        avg = sum(float(q["response_time_ms"]) for q in success_queries) / len(success_queries)
        run["summary"]["avg_response_ms"] = round(avg, 2)

    run_file.write_text(json.dumps(run, indent=2), encoding="utf-8")
    print(f"\nSaved run file: {run_file}")

    history_record = {
        "run_file": str(run_file),
        "run_timestamp": run["run_timestamp"],
        "upload_success": run["summary"]["upload_success"],
        "upload_fail": run["summary"]["upload_fail"],
        "query_success": run["summary"]["query_success"],
        "query_fail": run["summary"]["query_fail"],
        "not_found_count": run["summary"]["not_found_count"],
        "avg_response_ms": run["summary"]["avg_response_ms"],
    }
    with history_file.open("a", encoding="utf-8") as f:
        f.write(json.dumps(history_record) + os.linesep)
    print(f"Appended history: {history_file}")

    result_files = sorted(RESULTS_DIR.glob("test_results_*.json"), key=lambda p: p.stat().st_mtime)
    prev_file = result_files[-2] if len(result_files) >= 2 else None
    build_report(prev_file, run_file, report_file)
    print(f"Generated report: {report_file}")
    print("\nDone.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
