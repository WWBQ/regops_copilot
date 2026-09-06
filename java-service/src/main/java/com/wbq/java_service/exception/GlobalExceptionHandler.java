package com.wbq.java_service.exception;

import java.util.Map;

import com.wbq.java_service.dto.common.ApiError;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.FieldError;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class GlobalExceptionHandler {

    @ExceptionHandler(ToolAccessException.class)
    public ResponseEntity<ApiError> handleToolAccess(ToolAccessException ex) {
        return ResponseEntity.status(ex.getStatus())
                .body(new ApiError(ex.getMessage(), Map.of("error_code", ex.getErrorCode())));
    }

    @ExceptionHandler(PythonAiException.class)
    public ResponseEntity<ApiError> handlePythonAi(PythonAiException ex) {
        HttpStatus status = HttpStatus.resolve(ex.getStatusCode());
        if (status == null) {
            status = HttpStatus.BAD_GATEWAY;
        }
        return ResponseEntity.status(status).body(new ApiError(ex.getMessage()));
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<ApiError> handleValidation(MethodArgumentNotValidException ex) {
        FieldError fieldError = ex.getBindingResult().getFieldError();
        String detail = fieldError != null ? fieldError.getDefaultMessage() : "validation failed";
        return ResponseEntity.badRequest().body(new ApiError(detail));
    }

    @ExceptionHandler(Exception.class)
    public ResponseEntity<ApiError> handleGeneric(Exception ex) {
        return ResponseEntity.internalServerError().body(new ApiError(ex.getMessage()));
    }
}
