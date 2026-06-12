"""
日志系统 — 基于 loguru 的统一日志管理。

配置说明：
  - 控制台输出：彩色格式，开发时实时查看
  - 文件输出：按天轮转，保留 30 天，自动压缩旧日志
  - 日志级别：默认 INFO（生产可调为 WARNING），通过 .env 的 LOG_LEVEL 控制

日志格式：
  时间 | 级别 | 模块:行号 | 消息

使用方式：
  from app.core.logger import logger
  logger.info("用户上传了文件 {}", filename)
  logger.error("Milvus 连接失败: {}", error)
"""

import sys
from pathlib import Path
from loguru import logger

# 全局初始化标记
_initialized = False


def setup_logger(
    log_level: str = "INFO",
    log_dir: str = "logs",
    rotation: str = "00:00",      # 每天午夜轮转
    retention: str = "30 days",   # 保留 30 天
    compression: str = "gz",      # 旧日志压缩为 .gz
):
    """配置 loguru 日志系统。

    只需在应用启动时调用一次。后续所有模块通过
    `from app.core.logger import logger` 使用同一个实例。

    Args:
        log_level:  日志级别（DEBUG / INFO / WARNING / ERROR）
        log_dir:    日志文件目录
        rotation:   轮转策略（"00:00" = 每天午夜切新文件）
        retention:  旧日志保留时间
        compression: 旧日志压缩格式
    """
    global _initialized
    if _initialized:
        return
    _initialized = True

    # 1. 移除默认的 handler（loguru 默认有一个 stderr handler）
    logger.remove()

    # 2. 添加控制台输出 — 彩色格式，方便开发调试
    logger.add(
        sys.stderr,
        level=log_level,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{line}</cyan> | "
            "<level>{message}</level>"
        ),
        colorize=True,
    )

    # 3. 添加文件输出 — 按天轮转，保留 30 天
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    logger.add(
        log_path / "aioperator_{time:YYYY-MM-DD}.log",
        level=log_level,
        format=(
            "{time:YYYY-MM-DD HH:mm:ss.SSS} | "
            "{level: <8} | "
            "{name}:{line} | "
            "{message}"
        ),
        rotation=rotation,
        retention=retention,
        compression=compression,
        encoding="utf-8",
    )

    logger.info("日志系统初始化完成 — 级别: {}, 目录: {}", log_level, log_dir)


# 导出 logger 实例，其他模块直接 `from app.core.logger import logger`
__all__ = ["logger", "setup_logger"]
