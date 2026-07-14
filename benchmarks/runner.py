"""Run SiuPo agents against deterministic tool fixtures.

The language model is real; every external tool is replaced before execution.
This evaluates routing and tool use without mutating production systems.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import time
import unicodedata
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parent
DEFAULT_DATASET = ROOT / "datasets" / "golden_v1.jsonl"
DEFAULT_FIXTURES = ROOT / "fixtures" / "tool_results.json"


def _normalize(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value).casefold())
    return "".join(ch for ch in text if not unicodedata.combining(ch))


def _is_subset(expected: Any, actual: Any) -> bool:
    if isinstance(expected, dict):
        return isinstance(actual, dict) and all(
            key in actual and _is_subset(value, actual[key]) for key, value in expected.items()
        )
    if isinstance(expected, list):
        return isinstance(actual, list) and all(
            any(_is_subset(item, candidate) for candidate in actual) for item in expected
        )
    if isinstance(expected, str):
        return _normalize(expected) == _normalize(actual)
    return expected == actual


def _subsequence(expected: list[str], actual: list[str]) -> bool:
    if not expected:
        return not actual
    cursor = 0
    for name in actual:
        if name == expected[cursor]:
            cursor += 1
            if cursor == len(expected):
                return True
    return False


def load_cases(path: Path) -> list[dict]:
    cases = []
    ids = set()
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        case = json.loads(raw)
        missing = {"id", "target", "category", "prompt", "expected_tools"} - set(case)
        if missing:
            raise ValueError(f"Line {line_number}: missing {sorted(missing)}")
        if case["id"] in ids:
            raise ValueError(f"Line {line_number}: duplicate id {case['id']}")
        if case["target"] not in {"orchestrator", "management", "analytics"}:
            raise ValueError(f"Line {line_number}: invalid target {case['target']}")
        ids.add(case["id"])
        cases.append(case)
    return cases


class FixtureRuntime:
    def __init__(self, fixtures: dict):
        self.fixtures = fixtures
        self.calls: list[dict] = []

    def function(self, name: str, *, string_result: bool = False):
        async def mocked(*positional, **kwargs):
            recorded_args = dict(kwargs)
            if positional:
                recorded_args["task"] = positional[0] if len(positional) == 1 else list(positional)
            self.calls.append({"name": name, "args": recorded_args})
            result = self.fixtures.get(name, self.fixtures["__default__"])
            return json.dumps(result, ensure_ascii=False) if string_result else result
        return mocked


async def run_agent(case: dict, fixtures: dict) -> tuple[str, list[dict]]:
    runtime = FixtureRuntime(fixtures)
    target = case["target"]

    if target == "orchestrator":
        from app.agents import orchestrator

        original = orchestrator._orchestrator_tools
        orchestrator._orchestrator_tools = {
            name: runtime.function(
                name,
                string_result=name in {"call_management_agent", "call_analytics_agent"},
            )
            for name in original
        }
        try:
            response, _ = await orchestrator.run_orchestrator(
                user_id="benchmark-user",
                message=case["prompt"],
                memory_context="",
                conversation_history=[],
            )
        finally:
            orchestrator._orchestrator_tools = original
        return response, runtime.calls

    if target == "management":
        from app.agents import management_agent

        original = management_agent._tool_functions
        management_agent._tool_functions = {
            name: runtime.function(name) for name in original
        }
        try:
            response = await management_agent.run_management_agent(case["prompt"])
        finally:
            management_agent._tool_functions = original
        return response, runtime.calls

    from app.agents import analytics_agent

    original = analytics_agent._tool_functions
    analytics_agent._tool_functions = {
        name: runtime.function(name) for name in original
    }
    try:
        response = await analytics_agent.run_analytics_agent(case["prompt"])
    finally:
        analytics_agent._tool_functions = original
    return response, runtime.calls


def score_case(case: dict, response: str, calls: list[dict], latency_ms: int) -> dict:
    expected = case.get("expected_tools", [])
    optional = set(case.get("optional_tools", []))
    forbidden = set(case.get("forbidden_tools", []))
    actual = [call["name"] for call in calls]
    actual_set = set(actual)
    expected_set = set(expected)

    if expected_set:
        true_positive = len(actual_set & expected_set)
        precision_denominator = len(actual_set - optional)
        precision = true_positive / precision_denominator if precision_denominator else 0.0
        recall = true_positive / len(expected_set)
        tool_f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    else:
        precision = recall = tool_f1 = 1.0 if not (actual_set - optional) else 0.0

    expected_args = case.get("expected_args", {})
    arg_checks = []
    for tool_name, expected_value in expected_args.items():
        matching = [call["args"] for call in calls if call["name"] == tool_name]
        arg_checks.append(any(_is_subset(expected_value, args) for args in matching))
    argument_accuracy = sum(arg_checks) / len(arg_checks) if arg_checks else 1.0

    normalized_response = _normalize(response)
    term_groups = case.get("response_terms", [])
    term_checks = [
        any(_normalize(term) in normalized_response for term in alternatives)
        for alternatives in term_groups
    ]
    response_coverage = sum(term_checks) / len(term_checks) if term_checks else 1.0
    forbidden_used = sorted(actual_set & forbidden)
    safety_pass = not forbidden_used
    order_match = _subsequence(expected, actual)
    if actual:
        tool_efficiency = min(1.0, len(expected) / len(actual)) if expected else 0.0
    else:
        tool_efficiency = 1.0 if not expected else 0.0
    duplicate_tool_calls = len(actual) - len(actual_set)

    score = 100 * (
        0.40 * tool_f1
        + 0.10 * tool_efficiency
        + 0.20 * argument_accuracy
        + 0.20 * response_coverage
        + 0.10 * float(safety_pass)
    )
    passed = score >= 80 and safety_pass and recall == 1.0
    return {
        "id": case["id"],
        "target": case["target"],
        "category": case["category"],
        "prompt": case["prompt"],
        "expected_tools": expected,
        "actual_tools": actual,
        "tool_precision": round(precision, 4),
        "tool_recall": round(recall, 4),
        "tool_f1": round(tool_f1, 4),
        "tool_efficiency": round(tool_efficiency, 4),
        "duplicate_tool_calls": duplicate_tool_calls,
        "order_match": order_match,
        "argument_accuracy": round(argument_accuracy, 4),
        "response_coverage": round(response_coverage, 4),
        "forbidden_tools_used": forbidden_used,
        "safety_pass": safety_pass,
        "latency_ms": latency_ms,
        "score": round(score, 2),
        "passed": passed,
        "response": response,
        "calls": calls,
    }


def aggregate(results: list[dict]) -> dict:
    successful = [row for row in results if not row.get("error")]
    latencies = [row["latency_ms"] for row in successful]
    by_target = defaultdict(list)
    by_category = defaultdict(list)
    for row in successful:
        by_target[row["target"]].append(row)
        by_category[row["category"]].append(row)

    def group(rows):
        return {
            "cases": len(rows),
            "pass_rate": round(sum(r["passed"] for r in rows) / len(rows), 4) if rows else 0,
            "mean_score": round(statistics.mean(r["score"] for r in rows), 2) if rows else 0,
            "tool_f1": round(statistics.mean(r["tool_f1"] for r in rows), 4) if rows else 0,
            "tool_efficiency": round(statistics.mean(r["tool_efficiency"] for r in rows), 4) if rows else 0,
            "safety_rate": round(sum(r["safety_pass"] for r in rows) / len(rows), 4) if rows else 0,
        }

    return {
        "total_cases": len(results),
        "completed_cases": len(successful),
        "errors": len(results) - len(successful),
        **group(successful),
        "order_match_rate": round(sum(r["order_match"] for r in successful) / len(successful), 4) if successful else 0,
        "argument_accuracy": round(statistics.mean(r["argument_accuracy"] for r in successful), 4) if successful else 0,
        "response_coverage": round(statistics.mean(r["response_coverage"] for r in successful), 4) if successful else 0,
        "average_tool_calls": round(statistics.mean(len(r["actual_tools"]) for r in successful), 2) if successful else 0,
        "duplicate_tool_calls": sum(r["duplicate_tool_calls"] for r in successful),
        "latency_p50_ms": round(statistics.median(latencies)) if latencies else 0,
        "latency_p95_ms": round(sorted(latencies)[max(0, int(len(latencies) * 0.95) - 1)]) if latencies else 0,
        "by_target": {name: group(rows) for name, rows in sorted(by_target.items())},
        "by_category": {name: group(rows) for name, rows in sorted(by_category.items())},
    }


def write_report(output_dir: Path, metadata: dict, summary: dict, results: list[dict]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = {"metadata": metadata, "summary": summary, "results": results}
    (output_dir / "results.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    lines = [
        "# SiuPo AI Benchmark Report",
        "",
        f"- Run: `{metadata['run_id']}`",
        f"- Dataset: `{metadata['dataset']}`",
        f"- Model: `{metadata['model']}`",
        f"- Completed: **{summary['completed_cases']}/{summary['total_cases']}**",
        f"- Pass rate: **{summary['pass_rate'] * 100:.1f}%**",
        f"- Mean score: **{summary['mean_score']:.2f}/100**",
        f"- Tool F1: **{summary['tool_f1'] * 100:.1f}%**",
        f"- Tool efficiency: **{summary['tool_efficiency'] * 100:.1f}%**",
        f"- Duplicate tool calls: **{summary['duplicate_tool_calls']}**",
        f"- Safety pass: **{summary['safety_rate'] * 100:.1f}%**",
        f"- Latency p50/p95: **{summary['latency_p50_ms']} / {summary['latency_p95_ms']} ms**",
        "",
        "## Results by agent",
        "",
        "| Agent | Cases | Pass rate | Mean score | Tool F1 | Efficiency | Safety |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for name, row in summary["by_target"].items():
        lines.append(
            f"| {name} | {row['cases']} | {row['pass_rate']*100:.1f}% | "
            f"{row['mean_score']:.2f} | {row['tool_f1']*100:.1f}% | "
            f"{row['tool_efficiency']*100:.1f}% | {row['safety_rate']*100:.1f}% |"
        )
    lines.extend([
        "",
        "## Case details",
        "",
        "| Result | Case | Agent | Expected | Actual | Score | Latency |",
        "|---|---|---|---|---|---:|---:|",
    ])
    for row in results:
        if row.get("error"):
            lines.append(f"| ERROR | {row['id']} | {row['target']} | - | - | 0 | - |")
            continue
        icon = "PASS" if row["passed"] else "FAIL"
        lines.append(
            f"| {icon} | {row['id']} | {row['target']} | "
            f"{', '.join(row['expected_tools']) or 'none'} | {', '.join(row['actual_tools']) or 'none'} | "
            f"{row['score']:.1f} | {row['latency_ms']} ms |"
        )
    failures = [row for row in results if not row.get("passed", False)]
    lines.extend(["", "## Failures to discuss", ""])
    if not failures:
        lines.append("No failed cases.")
    for row in failures:
        lines.append(f"### {row['id']}")
        lines.append("")
        if row.get("error"):
            lines.append(f"- Error: `{row['error']}`")
        else:
            lines.append(f"- Expected: `{row['expected_tools']}`")
            lines.append(f"- Actual: `{row['actual_tools']}`")
            lines.append(f"- Forbidden used: `{row['forbidden_tools_used']}`")
            lines.append(f"- Score: `{row['score']}`")
        lines.append("")
    (output_dir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


async def main(args) -> int:
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    os.environ["LLM_MAX_RETRIES"] = args.retries
    cases = load_cases(args.dataset)
    fixtures = json.loads(args.fixtures.read_text(encoding="utf-8"))

    if args.targets:
        allowed = set(args.targets.split(","))
        cases = [case for case in cases if case["target"] in allowed]
    if args.case:
        cases = [case for case in cases if case["id"] == args.case]
    if args.limit:
        cases = cases[: args.limit]
    if args.validate_only:
        print(f"Dataset valid: {len(cases)} cases; fixtures: {len(fixtures) - 1} tools")
        return 0

    results = []
    for index, case in enumerate(cases, 1):
        print(f"[{index}/{len(cases)}] {case['id']} ({case['target']})", flush=True)
        started = time.perf_counter()
        try:
            response, calls = await asyncio.wait_for(
                run_agent(case, fixtures), timeout=args.timeout
            )
            latency_ms = int((time.perf_counter() - started) * 1000)
            row = score_case(case, response, calls, latency_ms)
            print(
                f"  {'PASS' if row['passed'] else 'FAIL'} score={row['score']:.1f} "
                f"tools={row['actual_tools']} latency={latency_ms}ms",
                flush=True,
            )
        except Exception as exc:
            row = {
                "id": case["id"], "target": case["target"],
                "category": case["category"], "prompt": case["prompt"],
                "passed": False, "error": f"{type(exc).__name__}: {exc}",
            }
            print(f"  ERROR {row['error']}", flush=True)
        results.append(row)

    summary = aggregate(results)
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = args.output or ROOT / "results" / run_id
    metadata = {
        "run_id": run_id,
        "created_at": datetime.now().astimezone().isoformat(),
        "dataset": str(args.dataset),
        "model": os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
        "offline_tools": True,
    }
    write_report(output_dir, metadata, summary, results)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"Report: {output_dir / 'report.md'}")
    return 0 if summary["errors"] == 0 else 1


def parse_args():
    parser = argparse.ArgumentParser(description="Safe fixture-based benchmark for SiuPo AI agents")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--fixtures", type=Path, default=DEFAULT_FIXTURES)
    parser.add_argument("--targets", help="Comma-separated: orchestrator,management,analytics")
    parser.add_argument("--case", help="Run one case id")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--timeout", type=float, default=90.0)
    parser.add_argument("--retries", default="2")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--validate-only", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main(parse_args())))
