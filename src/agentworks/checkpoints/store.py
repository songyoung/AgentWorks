"""检查点存储 —— SQLite 数据库连接与 SqliteSaver。

数据库选型: SQLite（嵌入式、单文件、无需独立服务进程）
依赖驱动: langgraph-checkpoint-sqlite
配置来源: harness_spec.yaml + 环境变量 CHECKPOINT_DB_PATH
"""

from __future__ import annotations

import os
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver

from agentworks.core.config import get_harness_spec


def get_checkpoint_db_path() -> str:
    """获取检查点数据库文件路径。

    优先级: 环境变量 > harness_spec.yaml > 默认路径。
    """
    spec = get_harness_spec()
    default_path = spec.checkpoint.default_db_path
    return os.environ.get(spec.checkpoint.db_path_env, str(Path(default_path).resolve()))


def get_checkpoint_table_name() -> str:
    """获取检查点表名（从 harness_spec.yaml 读取）。"""
    spec = get_harness_spec()
    return spec.checkpoint.table_name


@contextmanager
def create_checkpointer() -> Generator[SqliteSaver, None, None]:
    """创建 SqliteSaver 检查点存储实例（上下文管理器）。

    表结构由 langgraph 的 SqliteSaver 在首次启动时自动创建。

    Usage:
        with create_checkpointer() as checkpointer:
            graph = get_graph(checkpointer=checkpointer)

    Yields:
        SqliteSaver 实例。
    """
    db_path = get_checkpoint_db_path()
    with SqliteSaver.from_conn_string(db_path) as saver:
        yield saver
