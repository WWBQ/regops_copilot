package com.wbq.java_service.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "regops")
public record AppProperties(PythonAiProperties pythonAi) {

    public record PythonAiProperties(
            String baseUrl,
            long connectTimeoutMs,
            long readTimeoutMs,
            String serviceName,
            String serviceToken,
            Integer readRetryCount
    ) {
        public PythonAiProperties {
            if (serviceName == null || serviceName.isBlank()) {
                serviceName = "java-service";
            }
            if (serviceToken == null) {
                serviceToken = "";
            }
        }

        public int resolvedReadRetryCount() {
            return readRetryCount == null ? 2 : Math.max(0, readRetryCount);
        }
    }
}
