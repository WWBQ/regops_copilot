package com.wbq.java_service.exception;

public class PythonAiException extends RuntimeException {

    private final int statusCode;

    public PythonAiException(int statusCode, String message) {
        super(message);
        this.statusCode = statusCode;
    }

    public int getStatusCode() {
        return statusCode;
    }
}
