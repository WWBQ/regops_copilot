package com.wbq.java_service.exception;

import java.util.LinkedHashMap;
import java.util.Map;

import com.wbq.java_service.dto.common.ApiError;
import com.wbq.java_service.filter.RequestIdFilter;

import org.slf4j.MDC;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.orm.ObjectOptimisticLockingFailureException;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.validation.FieldError;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class GlobalExceptionHandler {

    @ExceptionHandler(BusinessException.class)
    public ResponseEntity<ApiError> handleBusiness(BusinessException ex) {
        return ResponseEntity.status(ex.getStatus())
                .body(new ApiError(ex.getMessage(), extra("error_code", ex.getErrorCode())));
    }

    @ExceptionHandler(AccessDeniedException.class)
    public ResponseEntity<ApiError> handleAccessDenied(AccessDeniedException ex) {
        return ResponseEntity.status(HttpStatus.FORBIDDEN)
                .body(new ApiError("无权访问", extra("error_code", "unauthorized")));
    }

    @ExceptionHandler(ObjectOptimisticLockingFailureException.class)
    public ResponseEntity<ApiError> handleOptimistic(ObjectOptimisticLockingFailureException ex) {
        return ResponseEntity.status(HttpStatus.CONFLICT)
                .body(new ApiError("并发更新冲突", extra("error_code", "conflict")));
    }

    @ExceptionHandler(PythonAiException.class)
    public ResponseEntity<ApiError> handlePythonAi(PythonAiException ex) {
        HttpStatus status = HttpStatus.resolve(ex.getStatusCode());
        if (status == null) {
            status = HttpStatus.BAD_GATEWAY;
        }
        return ResponseEntity.status(status)
                .body(new ApiError(ex.getMessage(), extra("error_code", ex.getErrorCode())));
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<ApiError> handleValidation(MethodArgumentNotValidException ex) {
        FieldError fieldError = ex.getBindingResult().getFieldError();
        String detail = fieldError != null ? fieldError.getDefaultMessage() : "validation failed";
        return ResponseEntity.badRequest().body(new ApiError(detail, extra("error_code", "invalid_params")));
    }

    @ExceptionHandler(Exception.class)
    public ResponseEntity<ApiError> handleGeneric(Exception ex) {
        return ResponseEntity.internalServerError()
                .body(new ApiError(ex.getMessage(), extra("error_code", "internal_error")));
    }

    private static Map<String, Object> extra(String key, String value) {
        Map<String, Object> extra = new LinkedHashMap<>();
        extra.put(key, value);
        String requestId = MDC.get(RequestIdFilter.MDC_KEY);
        if (requestId != null && !requestId.isBlank()) {
            extra.put("request_id", requestId);
        }
        return extra;
    }
}
