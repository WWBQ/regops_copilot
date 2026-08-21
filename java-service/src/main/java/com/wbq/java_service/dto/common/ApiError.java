package com.wbq.java_service.dto.common;

import java.util.Map;

public record ApiError(
        String detail,
        Map<String, Object> extra
) {
    public ApiError(String detail) {
        this(detail, Map.of());
    }
}
