"""FastAPI 应用入口模块。

本模块是金融风险审计助手后端的服务入口，负责：
- 加载环境变量和日志配置
- 创建 FastAPI 应用实例
- 注册所有 API 路由
"""
from __future__ import annotations

from fastapi import FastAPI

from agent.core.logging_config import configure_logging
from agent.env_utils import load_environment

# ---------------------------------------------------------------
# 启动前置初始化
# ---------------------------------------------------------------
# 注意：FastAPI/Uvicorn 是本课程版本中唯一的服务化入口。
# 这里显式调用 load_environment() 加载 .env 文件中的配置，
# 并调用 configure_logging() 初始化日志系统。
# 这样做的好处是不依赖 langgraph dev 等开发服务器自带的环境加载机制。
# ---------------------------------------------------------------
load_environment()
configure_logging()

# 延迟导入 API 路由模块
# 使用 # noqa: E402 忽略 flake8 关于导入顺序的警告，
# 因为此处必须等环境变量和日志配置初始化完成后才能导入路由模块。
from agent.api import health_router, risk_agent_router  # noqa: E402

# ---------------------------------------------------------------
# 创建 FastAPI 应用实例
# ---------------------------------------------------------------
app = FastAPI(
    title="金融风险审计助手 API",  # 应用名称
    version="0.1.0",                     # 应用版本号
)

# ---------------------------------------------------------------
# 注册路由
# ---------------------------------------------------------------
# health_router - 健康检查
# risk_agent_router - RegOps 金融初筛页面的会话与流式接口
# ---------------------------------------------------------------
app.include_router(health_router)
app.include_router(risk_agent_router)
