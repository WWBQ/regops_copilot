package com.wbq.java_service.dto.common;

import java.util.Map;

public record ServiceHealthResponse(
        String status,
        String service,
        Map<String, Object> pythonAi
) {
}
