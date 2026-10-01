package com.wbq.java_service.dto.chat;

import java.util.List;
import java.util.Map;

import com.fasterxml.jackson.annotation.JsonProperty;

public record ChatResponse(
        String reply,
        String model,
        String disclaimer,
        List<Citation> citations,
        @JsonProperty("session_id") String sessionId,
        @JsonProperty("rag_used") boolean ragUsed,
        String route,
        @JsonProperty("prompt_tokens") int promptTokens,
        @JsonProperty("completion_tokens") int completionTokens,
        @JsonProperty("total_tokens") int totalTokens,
        @JsonProperty("latency_ms") double latencyMs,
        @JsonProperty("total_latency_ms") double totalLatencyMs,
        @JsonProperty("pending_request") Map<String, Object> pendingRequest,
        Map<String, Object> comparison
) {
    public ChatResponse {
        if (citations == null) {
            citations = List.of();
        }
        if (route == null || route.isBlank()) {
            route = "general";
        }
    }

    public ChatResponse(
            String reply,
            String model,
            String disclaimer,
            List<Citation> citations,
            String sessionId,
            boolean ragUsed,
            String route,
            int promptTokens,
            int completionTokens,
            int totalTokens,
            double latencyMs,
            Map<String, Object> pendingRequest
    ) {
        this(
                reply,
                model,
                disclaimer,
                citations,
                sessionId,
                ragUsed,
                route,
                promptTokens,
                completionTokens,
                totalTokens,
                latencyMs,
                latencyMs,
                pendingRequest,
                null
        );
    }
}
