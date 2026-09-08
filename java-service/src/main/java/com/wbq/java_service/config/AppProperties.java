package com.wbq.java_service.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "regops")
public record AppProperties(PythonAiProperties pythonAi, AuthProperties auth) {

    public AppProperties {
        if (auth == null) {
            auth = new AuthProperties("dev-regops-jwt-secret-change-me-32b", 28_800L, true);
        }
    }

    public record PythonAiProperties(
            String baseUrl,
            long connectTimeoutMs,
            long readTimeoutMs,
            Long streamTimeoutMs,
            Long healthTimeoutMs,
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

        public long resolvedHealthTimeoutMs() {
            return healthTimeoutMs == null || healthTimeoutMs <= 0 ? 2_500L : healthTimeoutMs;
        }

        public long resolvedStreamTimeoutMs() {
            long stream = streamTimeoutMs == null || streamTimeoutMs <= 0 ? 180_000L : streamTimeoutMs;
            return Math.max(readTimeoutMs, stream);
        }
    }

    public record AuthProperties(String jwtSecret, Long jwtTtlSeconds, Boolean seed) {
        public AuthProperties {
            if (jwtSecret == null || jwtSecret.length() < 32) {
                jwtSecret = "dev-regops-jwt-secret-change-me-32b";
            }
            if (jwtTtlSeconds == null || jwtTtlSeconds <= 0) {
                jwtTtlSeconds = 28_800L;
            }
            if (seed == null) {
                seed = true;
            }
        }

        public boolean seedEnabled() {
            return Boolean.TRUE.equals(seed);
        }

        public long ttlSeconds() {
            return jwtTtlSeconds;
        }
    }
}
