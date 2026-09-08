package com.wbq.java_service.client;

import java.net.ConnectException;
import java.net.NoRouteToHostException;
import java.net.SocketTimeoutException;
import java.net.UnknownHostException;
import java.net.http.HttpTimeoutException;
import java.util.Locale;
import java.util.concurrent.TimeoutException;

import com.wbq.java_service.exception.PythonAiException;

import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;

/**
 * 把 python-ai 的 HTTP / 传输失败收成稳定的 {@link PythonAiException}，
 * 不把 FastAPI JSON 原文或堆栈泄漏给浏览器。
 */
public final class PythonErrorMapper {

    private static final JsonMapper JSON = JsonMapper.builder().build();
    private static final int DETAIL_LIMIT = 400;

    private PythonErrorMapper() {
    }

    public static PythonAiException fromDownstream(int status, String body) {
        String detail = parseDetail(body);
        if (detail == null || detail.isBlank()) {
            detail = "python-ai HTTP " + status;
        }
        return new PythonAiException(status, clip(detail), PythonAiException.defaultErrorCode(status));
    }

    public static PythonAiException fromTransport(Throwable ex) {
        if (isConnectFailure(ex)) {
            return new PythonAiException(502, "python-ai unavailable", "upstream_down");
        }
        if (isTimeout(ex)) {
            return new PythonAiException(504, "python-ai timeout", "upstream_timeout");
        }
        return new PythonAiException(502, "python-ai unavailable", "upstream_down");
    }

    static String parseDetail(String body) {
        if (body == null || body.isBlank()) {
            return null;
        }
        String trimmed = body.strip();
        try {
            JsonNode root = JSON.readTree(trimmed);
            JsonNode detail = root.get("detail");
            if (detail == null || detail.isNull()) {
                return clip(trimmed);
            }
            if (detail.isString()) {
                return clip(detail.asString());
            }
            if (detail.isArray()) {
                StringBuilder joined = new StringBuilder();
                for (JsonNode item : detail) {
                    String piece = itemMessage(item);
                    if (piece == null || piece.isBlank()) {
                        continue;
                    }
                    if (!joined.isEmpty()) {
                        joined.append("；");
                    }
                    joined.append(piece);
                }
                return joined.isEmpty() ? clip(trimmed) : clip(joined.toString());
            }
            return clip(detail.toString());
        } catch (Exception ignored) {
            return clip(trimmed);
        }
    }

    private static String itemMessage(JsonNode item) {
        if (item == null || item.isNull()) {
            return null;
        }
        if (item.isString()) {
            return item.asString();
        }
        JsonNode msg = item.get("msg");
        if (msg != null && msg.isString()) {
            return msg.asString();
        }
        return item.toString();
    }

    private static boolean isConnectFailure(Throwable ex) {
        Throwable current = ex;
        while (current != null) {
            if (current instanceof ConnectException
                    || current instanceof UnknownHostException
                    || current instanceof NoRouteToHostException) {
                return true;
            }
            String message = current.getMessage();
            if (message != null) {
                String lower = message.toLowerCase(Locale.ROOT);
                if (lower.contains("connection refused")
                        || lower.contains("connect timed out")
                        || lower.contains("failed to connect")
                        || lower.contains("connection reset")) {
                    return true;
                }
            }
            current = current.getCause();
        }
        return false;
    }

    private static boolean isTimeout(Throwable ex) {
        Throwable current = ex;
        while (current != null) {
            if (current instanceof SocketTimeoutException
                    || current instanceof HttpTimeoutException
                    || current instanceof TimeoutException) {
                return true;
            }
            String message = current.getMessage();
            if (message != null) {
                String lower = message.toLowerCase(Locale.ROOT);
                if (lower.contains("read timed out")
                        || lower.contains("timeout")
                        || lower.contains("timed out")) {
                    return true;
                }
            }
            current = current.getCause();
        }
        return false;
    }

    private static String clip(String text) {
        if (text == null) {
            return null;
        }
        String stripped = text.strip();
        if (stripped.length() <= DETAIL_LIMIT) {
            return stripped;
        }
        return stripped.substring(0, DETAIL_LIMIT);
    }
}
