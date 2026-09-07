package com.wbq.java_service.dto.chat;

import java.util.List;

import com.fasterxml.jackson.annotation.JsonProperty;

import jakarta.validation.constraints.DecimalMax;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record ChatRequest(
        @NotBlank @Size(max = 16000) String message,
        @DecimalMin("0.0") @DecimalMax("2.0") Double temperature,
        @JsonProperty("session_id") String sessionId,
        @JsonProperty("use_rag") Boolean useRag,
        String model,
        @JsonProperty("thread_id") String threadId
) {
    public ChatRequest {
        if (temperature == null) {
            temperature = 0.1;
        }
        if (useRag == null) {
            useRag = true;
        }
    }
}
