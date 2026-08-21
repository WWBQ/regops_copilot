package com.wbq.java_service.dto.sessions;

import java.time.OffsetDateTime;

import com.fasterxml.jackson.annotation.JsonProperty;

public record SessionDocumentResponse(
        @JsonProperty("doc_id") String docId,
        @JsonProperty("source_filename") String sourceFilename,
        @JsonProperty("job_id") String jobId,
        String status,
        @JsonProperty("page_count") Integer pageCount,
        @JsonProperty("chunk_count") Integer chunkCount,
        @JsonProperty("error_message") String errorMessage,
        @JsonProperty("created_at") OffsetDateTime createdAt,
        @JsonProperty("updated_at") OffsetDateTime updatedAt
) {
}
