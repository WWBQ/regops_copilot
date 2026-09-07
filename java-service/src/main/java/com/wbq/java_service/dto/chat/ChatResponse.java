package com.wbq.java_service.dto.chat;

import java.util.List;

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
        @JsonProperty("thread_id") String threadId,
        @JsonProperty("pending_node") String pendingNode
) {
    public ChatResponse {
        if (citations == null) {
            citations = List.of();
        }
        if (route == null || route.isBlank()) {
            route = "general";
        }
    }
}
