package com.wbq.java_service.dto.review;

import java.time.Instant;
import java.util.List;
import java.util.UUID;

import com.fasterxml.jackson.annotation.JsonInclude;
import com.wbq.java_service.review.TicketStatus;

@JsonInclude(JsonInclude.Include.NON_NULL)
public record TicketResponse(
        UUID id,
        TicketStatus status,
        String dept,
        String companyCode,
        List<String> companyCodes,
        String title,
        String reason,
        String conclusion,
        String riskLevel,
        List<String> clauseRefs,
        String impactScope,
        String threadId,
        String submittedBy,
        String reviewedBy,
        String reviewReason,
        String inputSummary,
        boolean replayed,
        Instant createdAt,
        Instant updatedAt
) {
}
