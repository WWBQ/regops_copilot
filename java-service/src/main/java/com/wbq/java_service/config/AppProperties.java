package com.wbq.java_service.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "regops")
public record AppProperties(PythonAiProperties pythonAi) {

    public record PythonAiProperties(
            String baseUrl,
            long connectTimeoutMs,
            long readTimeoutMs
    ) {
    }
}
