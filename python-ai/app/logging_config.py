import logging
import sys

from app.request_id import RequestIdLogFilter


def _ensure_request_id_filter(handler: logging.Handler) -> None:
    if not any(isinstance(item, RequestIdLogFilter) for item in handler.filters):
        handler.addFilter(RequestIdLogFilter())


def setup_logging(level: int = logging.INFO) -> None:
    """应用层日志：让 app.* 模块的 logger 输出到控制台。"""
    root = logging.getLogger()
    if not root.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)s [%(name)s] [%(request_id)s] [%(trace_id)s] %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        handler.addFilter(RequestIdLogFilter())
        root.addHandler(handler)
        root.setLevel(level)
    else:
        for handler in root.handlers:
            _ensure_request_id_filter(handler)
    logging.getLogger("app").setLevel(level)
