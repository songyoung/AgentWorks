"""CLI 入口 —— 命令行参数解析与图执行。

AgentWorks 通用 Agent 框架的命令行入口。通过 --input 传入任务描述，
框架自动执行 Loop Engineering 四阶段循环。

参数:
  --input        任务描述文本（必填）
  --thread-id    会话隔离标识（可选，默认生成 UUID）
  --max-retries  最大重试次数（可选，默认 3）
  --no-checkpoint 禁用检查点持久化

规则 R7: max_retries 默认值从 loop_spec.yaml 读取，CLI 参数可覆盖。
"""

from __future__ import annotations

import argparse
import sys
import uuid
from typing import Any

from agentworks.checkpoints.store import create_checkpointer
from agentworks.core.config import get_loop_spec
from agentworks.core.graph import get_graph


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(
        prog="agentworks",
        description="AgentWorks — 通用 Agent 开发框架 (LangGraph + Loop Engineering)",
    )

    parser.add_argument(
        "--input",
        type=str,
        required=True,
        help="任务描述文本（必填）",
    )

    parser.add_argument(
        "--thread-id",
        type=str,
        default=None,
        help="会话隔离标识（可选，默认生成 UUID）",
    )

    parser.add_argument(
        "--max-retries",
        type=int,
        default=None,
        help="最大重试次数（可选，默认从 loop_spec.yaml 读取）",
    )

    parser.add_argument(
        "--no-checkpoint",
        action="store_true",
        default=False,
        help="禁用检查点持久化",
    )

    return parser.parse_args(argv)


def _build_initial_state(args: argparse.Namespace) -> dict[str, Any]:
    """组装图执行的初始状态。

    Args:
        args: 命令行参数。

    Returns:
        符合 AgentState 的初始状态字典。
    """
    loop_spec = get_loop_spec()
    thread_id = args.thread_id or str(uuid.uuid4())
    max_retries = args.max_retries if args.max_retries is not None else loop_spec.max_retries

    return {
        "raw_input": args.input,
        "thread_id": thread_id,
        "parsed_structure": {},
        "context_summary": "",
        "task_plan": [],
        "generated_output": [],
        "quality_score": 0.0,
        "feedback": "",
        "messages": [],
        "retry_count": 0,
        "max_retries": max_retries,
        "is_complete": False,
    }


def main(argv: list[str] | None = None) -> None:
    """CLI 主入口 —— 组装状态并执行 Agent 循环图。"""
    args = parse_args(argv)
    initial_state = _build_initial_state(args)

    print("=" * 60)
    print("  AgentWorks — 通用 Agent 开发框架")
    print("  Loop Engineering: Gather → Action → Verify → Repeat")
    print("=" * 60)
    print(f"  Thread ID   : {initial_state['thread_id']}")
    print(f"  Max Retries : {initial_state['max_retries']}")
    print(f"  Checkpoint  : {'禁用' if args.no_checkpoint else '启用 (SQLite)'}")
    print(f"  Input       : {args.input[:80]}{'...' if len(args.input) > 80 else ''}")
    print("=" * 60)

    # ── 编译并运行图 ──
    config = {"configurable": {"thread_id": initial_state["thread_id"]}}

    try:
        if args.no_checkpoint:
            graph = get_graph()
            final_state = graph.invoke(initial_state, config)
        else:
            with create_checkpointer() as checkpointer:
                graph = get_graph(checkpointer=checkpointer)
                final_state = graph.invoke(initial_state, config)

        # ── 输出结果 ──
        _print_result(final_state)

    except KeyboardInterrupt:
        print("\n[中断] 用户取消执行。")
        sys.exit(1)
    except Exception as e:
        print(f"\n[错误] 图执行失败: {e}")
        sys.exit(1)


def _print_result(state: dict[str, Any]) -> None:
    """打印执行结果摘要。

    Args:
        state: 图执行后的最终状态。
    """
    print()
    print("─" * 60)
    print("  执行结果")
    print("─" * 60)
    print(f"  状态         : {'✅ 完成' if state.get('is_complete') else '⚠️ 未完成'}")
    print(f"  质量评分     : {state.get('quality_score', 0.0):.2%}")
    print(f"  重试次数     : {state.get('retry_count', 0)}")
    print(f"  反馈信息     : {state.get('feedback', '无')[:120]}")
    print(f"  任务计划步骤 : {len(state.get('task_plan', []))}")
    print(f"  输出条目数   : {len(state.get('generated_output', []))}")
    print("─" * 60)


if __name__ == "__main__":
    main()
