package com.wbq.java_service.dto.sessions;

import java.time.OffsetDateTime;

import com.fasterxml.jackson.annotation.JsonProperty;

public record SessionCreateResponse(
        @JsonProperty("session_id") String sessionId,
        @JsonProperty("expires_at") OffsetDateTime expiresAt
) {
}
