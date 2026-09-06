package com.wbq.java_service.dto.chat;

import com.fasterxml.jackson.annotation.JsonProperty;

public record Citation(
        @JsonProperty("doc_id") String docId,
        int page,
        String snippet,
        @JsonProperty("viewer_url") String viewerUrl,
        String title,
        String href,
        String kind
) {
}
