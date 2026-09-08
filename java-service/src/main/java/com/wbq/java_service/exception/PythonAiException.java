package com.wbq.java_service.exception;

public class PythonAiException extends RuntimeException {

    private final int statusCode;
    private final String errorCode;

    public PythonAiException(int statusCode, String message) {
        this(statusCode, message, defaultErrorCode(statusCode));
    }

    public PythonAiException(int statusCode, String message, String errorCode) {
        super(message);
        this.statusCode = statusCode;
        this.errorCode = errorCode == null || errorCode.isBlank()
                ? defaultErrorCode(statusCode)
                : errorCode;
    }

    public int getStatusCode() {
        return statusCode;
    }

    public String getErrorCode() {
        return errorCode;
    }

    public static String defaultErrorCode(int statusCode) {
        if (statusCode == 504) {
            return "upstream_timeout";
        }
        if (statusCode == 502 || statusCode == 503) {
            return "upstream_down";
        }
        if (statusCode >= 500) {
            return "upstream_error";
        }
        if (statusCode == 404) {
            return "not_found";
        }
        if (statusCode == 401 || statusCode == 403) {
            return "unauthorized";
        }
        if (statusCode >= 400) {
            return "upstream_client_error";
        }
        return "upstream_error";
    }
}
