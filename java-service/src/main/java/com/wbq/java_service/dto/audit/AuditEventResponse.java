package com.wbq.java_service.dto.audit;

import java.time.Instant;

public record AuditEventResponse(
        Long id,
        Instant occurredAt,
        String actorUsername,
        String actorRole,
        String dept,
        String action,
        String entityType,
        String entityId,
        String requestId,
        String reason,
        String inputSummary,
        String beforeJson,
        String afterJson
) {
}
