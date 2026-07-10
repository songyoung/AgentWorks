"""脚本流程梳理 Agent — 独立启动入口。

用法:
    cd workspace
    uv run python agents/script_flow/run.py --input sample_script.py

或通过 agentworks CLI 加载:
    uv run agentworks --input "$(cat sample_script.py)"
"""
from __future__ import annotations

import argparse
import sys
import uuid
from pathlib import Path
from typing import Any

# ── 导入 Agent 专属工具（触发 @register_tool 注册） ──
from agents.script_flow import tools  # noqa: F401 — 副作用导入

# ── 导入 AgentWorks 框架 ──
from agentworks.core.config import get_loop_spec
from agentworks.core.graph import get_graph
from agentworks.checkpoints.store import create_checkpointer


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(
        prog="script-flow-agent",
        description="脚本流程梳理 Agent — 分析代码控制流并生成 Mermaid 流程图",
    )
    parser.add_argument(
        "--input",
        type=str,
        required=True,
        help="要分析的脚本文件路径",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=None,
        help="最大重试次数（默认从配置读取）",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="输出报告文件路径（可选，默认打印到 stdout）",
    )
    return parser.parse_args(argv)


def _build_state(script_content: str, max_retries: int | None = None) -> dict[str, Any]:
    """组装初始状态。"""
    loop_spec = get_loop_spec()
    return {
        "raw_input": script_content,
        "thread_id": str(uuid.uuid4()),
        "parsed_structure": {},
        "context_summary": "",
        "task_plan": [],
        "generated_output": [],
        "quality_score": 0.0,
        "feedback": "",
        "messages": [],
        "retry_count": 0,
        "max_retries": max_retries if max_retries is not None else loop_spec.max_retries,
        "is_complete": False,
    }


def main(argv: list[str] | None = None) -> None:
    """Agent 主入口。"""
    args = parse_args(argv)

    # 读取脚本文件
    script_path = Path(args.input)
    if not script_path.exists():
        print(f"[错误] 文件不存在: {script_path}")
        sys.exit(1)
    script_content = script_path.read_text(encoding="utf-8")

    # 组装状态
    state = _build_state(script_content, args.max_retries)

    print("=" * 60)
    print("  脚本流程梳理 Agent")
    print("  Script Flow Analyzer")
    print("=" * 60)
    print(f"  分析文件 : {script_path.name}")
    print(f"  代码行数 : {len(script_content.splitlines())}")
    print(f"  最大重试 : {state['max_retries']}")
    print("=" * 60)
    print("  正在分析...")

    # 运行图
    config = {"configurable": {"thread_id": state["thread_id"]}}

    try:
        with create_checkpointer() as cp:
            graph = get_graph(checkpointer=cp)
            final_state = graph.invoke(state, config)
    except Exception as e:
        print(f"\n[错误] 执行失败: {e}")
        sys.exit(1)

    # 输出结果
    output = final_state.get("generated_output", [])
    quality = final_state.get("quality_score", 0.0)
    retries = final_state.get("retry_count", 0)

    print()
    print("─" * 60)
    print(f"  质量评分 : {quality:.0%}")
    print(f"  重试次数 : {retries}")
    print("─" * 60)

    if output:
        report_data = output[0] if isinstance(output, list) else output
        mermaid = report_data.get("mermaid", "")
        report = report_data.get("report", {})

        if mermaid:
            print("\n## Mermaid 流程图\n")
            print(mermaid)

        if report:
            print("\n## 分析报告\n")
            if isinstance(report, dict):
                summary = report.get("summary", "")
                if summary:
                    print(f"**概述**: {summary}\n")
                for key in ("key_paths", "risks", "suggestions"):
                    items = report.get(key, [])
                    if items:
                        label = {"key_paths": "关键路径", "risks": "风险点", "suggestions": "优化建议"}[key]
                        print(f"**{label}**:")
                        for item in items:
                            print(f"  - {item}")
                        print()

        # 可选：保存到文件
        if args.output:
            import json

            output_path = Path(args.output)
            output_path.write_text(
                json.dumps({"mermaid": mermaid, "report": report, "quality_score": quality}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            print(f"报告已保存到: {output_path}")
    else:
        print("  未生成输出内容。")
        feedback = final_state.get("feedback", "")
        if feedback:
            print(f"  反馈: {feedback}")

    print("─" * 60)


if __name__ == "__main__":
    main()
