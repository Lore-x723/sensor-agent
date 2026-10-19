"""A small, auditable sensor triage agent prototype."""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

FIELDS = ("timestamp", "device", "temperature_c", "vibration_mm_s")


def load_readings(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames or any(field not in reader.fieldnames for field in FIELDS):
            raise ValueError(f"CSV 必须包含列：{', '.join(FIELDS)}")
        readings = []
        for number, row in enumerate(reader, start=2):
            if not row["timestamp"] or not row["device"]:
                raise ValueError(f"第 {number} 行的时间或设备名为空")
            try:
                datetime.fromisoformat(row["timestamp"])
            except ValueError as exc:
                raise ValueError(f"第 {number} 行的时间不是 ISO 8601 格式") from exc
            try:
                temperature = float(row["temperature_c"])
                vibration = float(row["vibration_mm_s"])
            except (ValueError, TypeError) as exc:
                raise ValueError(f"第 {number} 行包含无效数值") from exc
            if not all(map(math.isfinite, (temperature, vibration))):
                raise ValueError(f"第 {number} 行包含非有限数值")
            readings.append({
                "timestamp": row["timestamp"],
                "device": row["device"],
                "temperature_c": temperature,
                "vibration_mm_s": vibration,
            })
    if not readings:
        raise ValueError("CSV 没有数据行")
    return readings


def latest_readings(readings: list[dict]) -> list[dict]:
    """Return the last row for each device; input is assumed chronological."""
    latest = {}
    for row in readings:
        latest[row["device"]] = row
    return list(latest.values())


def detect_anomalies(readings: list[dict], max_temp: float, max_vibration: float) -> list[dict]:
    results = []
    for row in readings:
        reasons = []
        if row["temperature_c"] > max_temp:
            reasons.append(f"温度 {row['temperature_c']:g} °C > {max_temp:g} °C")
        if row["vibration_mm_s"] > max_vibration:
            reasons.append(f"振动 {row['vibration_mm_s']:g} mm/s > {max_vibration:g} mm/s")
        if reasons:
            results.append({**row, "reasons": reasons})
    return results


def make_checklist(anomalies: list[dict], max_temp: float = 60, max_vibration: float = 4.5) -> list[dict]:
    checklist = []
    for item in anomalies:
        steps = ["核对传感器读数与采样时间，排除录入或通信错误"]
        if item["temperature_c"] > max_temp:
            steps.append("请负责人检查散热、负载和环境温度")
        if item["vibration_mm_s"] > max_vibration:
            steps.append("请负责人检查固定、轴承和运行声音")
        steps.append("记录复测结果，由负责人决定是否停机或报修")
        checklist.append({"device": item["device"], "timestamp": item["timestamp"], "steps": steps})
    return checklist


TOOLS = [
    {"type": "function", "function": {"name": "get_latest_readings", "description": "获取每台设备最近一次读数", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "find_anomalies", "description": "按演示阈值查询异常读数和证据", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "build_checklist", "description": "基于检测到的异常生成待人工审核的核查清单", "parameters": {"type": "object", "properties": {}}}},
]


def run_llm(readings: list[dict], anomalies: list[dict], checklist: list[dict]) -> str:
    key = os.environ.get("AGENT_API_KEY")
    base_url = os.environ.get("AGENT_BASE_URL")
    model = os.environ.get("AGENT_MODEL")
    if not all((key, base_url, model)):
        raise ValueError("--llm 需要 AGENT_API_KEY、AGENT_BASE_URL、AGENT_MODEL 三个环境变量")
    tool_results = {
        "get_latest_readings": latest_readings(readings),
        "find_anomalies": anomalies,
        "build_checklist": checklist,
    }
    messages = [
        {"role": "system", "content": "你是设备读数分析助手。请先调用工具取得证据，再用中文简要说明异常及建议。不要声称已接入真实硬件；不要直接下达停机命令；明确建议需要人工复核。"},
        {"role": "user", "content": "请分析设备最近的读数，指出异常并给出核查步骤。"},
    ]
    endpoint = base_url.rstrip("/") + "/chat/completions"
    for _ in range(5):
        payload = json.dumps({"model": model, "messages": messages, "tools": TOOLS, "tool_choice": "auto"}, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(endpoint, data=payload, headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                result = json.load(response)
        except (urllib.error.URLError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"模型接口请求失败：{exc}") from exc
        message = result["choices"][0]["message"]
        messages.append(message)
        calls = message.get("tool_calls") or []
        if not calls:
            return message.get("content") or "模型没有返回说明。"
        for call in calls:
            name = call["function"]["name"]
            value = tool_results.get(name, {"error": f"未知工具：{name}"})
            messages.append({"role": "tool", "tool_call_id": call["id"], "content": json.dumps(value, ensure_ascii=False)})
    raise RuntimeError("模型超过 5 轮工具调用，请缩小任务范围")


def main() -> int:
    parser = argparse.ArgumentParser(description="设备异常处置智能体原型（模拟数据）")
    parser.add_argument("--csv", type=Path, default=Path(__file__).with_name("sample_data.csv"))
    parser.add_argument("--demo", action="store_true", help="运行离线演示")
    parser.add_argument("--llm", action="store_true", help="启用兼容 Chat Completions 的模型工具调用")
    parser.add_argument("--max-temp", type=float, default=60.0)
    parser.add_argument("--max-vibration", type=float, default=4.5)
    args = parser.parse_args()
    try:
        if not all(map(math.isfinite, (args.max_temp, args.max_vibration))):
            raise ValueError("阈值必须是有限数值")
        readings = load_readings(args.csv)
        anomalies = detect_anomalies(readings, args.max_temp, args.max_vibration)
        checklist = make_checklist(anomalies, args.max_temp, args.max_vibration)
        if args.llm:
            print(run_llm(readings, anomalies, checklist))
            return 0
        print("设备异常处置智能体｜离线演示（模拟数据）")
        print(f"读取 {len(readings)} 条数据，发现 {len(anomalies)} 条异常。")
        if not anomalies:
            print("未发现超过演示阈值的读数。")
        for item, tasks in zip(anomalies, checklist):
            print(f"\n{item['timestamp']} | {item['device']} | {'；'.join(item['reasons'])}")
            for index, step in enumerate(tasks["steps"], 1):
                print(f"  {index}. {step}")
        print("\n说明：演示阈值和模拟数据未经真实设备验证，处置建议需要人工复核。")
        return 0
    except (OSError, ValueError, RuntimeError, KeyError, IndexError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
