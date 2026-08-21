package com.wbq.java_service.dto.sessions;

import java.util.List;

import com.fasterxml.jackson.annotation.JsonProperty;

public record SessionDocumentListResponse(
        @JsonProperty("session_id") String sessionId,
        List<SessionDocumentResponse> items
) {
}
