package com.wbq.java_service.dto.tools;

import java.util.Map;

import jakarta.validation.constraints.NotBlank;

public record ToolInvokeHttpRequest(
        @NotBlank String name,
        Map<String, Object> arguments,
        String backend
) {
}
