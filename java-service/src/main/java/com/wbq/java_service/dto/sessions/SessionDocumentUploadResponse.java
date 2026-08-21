package com.wbq.java_service.dto.sessions;

import com.fasterxml.jackson.annotation.JsonProperty;

public record SessionDocumentUploadResponse(
        @JsonProperty("session_id") String sessionId,
        @JsonProperty("doc_id") String docId,
        @JsonProperty("job_id") String jobId,
        String status,
        @JsonProperty("source_filename") String sourceFilename,
        String message
) {
}
