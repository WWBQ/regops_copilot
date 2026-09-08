package com.wbq.java_service.util;

import java.util.function.Supplier;

import com.wbq.java_service.exception.PythonAiException;

/**
 * 读请求有限重试：5xx / 网关失败可重试；4xx 与写路径不要走这里。
 */
public final class ReadRetry {

    private ReadRetry() {
    }

    public static <T> T call(int extraAttempts, Supplier<T> action) {
        int left = Math.max(0, extraAttempts);
        while (true) {
            try {
                return action.get();
            } catch (PythonAiException ex) {
                if (left <= 0 || !isRetryable(ex)) {
                    throw ex;
                }
                left--;
            }
        }
    }

    static boolean isRetryable(PythonAiException ex) {
        if (ex.getStatusCode() == 504 || "upstream_timeout".equals(ex.getErrorCode())) {
            return false;
        }
        return ex.getStatusCode() >= 500;
    }
}
