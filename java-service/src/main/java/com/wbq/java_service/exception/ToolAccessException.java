package com.wbq.java_service.exception;

import org.springframework.http.HttpStatus;

public class ToolAccessException extends RuntimeException {

    private final HttpStatus status;
    private final String errorCode;

    public ToolAccessException(String errorCode, String message) {
        this(HttpStatus.FORBIDDEN, errorCode, message);
    }

    public ToolAccessException(HttpStatus status, String errorCode, String message) {
        super(message);
        this.status = status;
        this.errorCode = errorCode;
    }

    public HttpStatus getStatus() {
        return status;
    }

    public String getErrorCode() {
        return errorCode;
    }
}
