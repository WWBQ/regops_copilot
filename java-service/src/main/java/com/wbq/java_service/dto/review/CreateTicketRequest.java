package com.wbq.java_service.dto.review;

import java.util.List;

import com.fasterxml.jackson.annotation.JsonProperty;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

public record CreateTicketRequest(
        @NotBlank
        @Pattern(regexp = "\\d{6}", message = "company_code 必须是 6 位证券代码")
        @JsonProperty("company_code")
        String companyCode,
        @NotBlank @Size(max = 120) String title,
        @NotBlank @Size(max = 500) String reason,
        @JsonProperty("company_codes") List<String> companyCodes,
        String conclusion,
        @JsonProperty("risk_level") String riskLevel,
        @JsonProperty("clause_refs") List<String> clauseRefs,
        @JsonProperty("evidence_quotes") List<String> evidenceQuotes,
        @JsonProperty("impact_scope") String impactScope,
        @JsonProperty("thread_id") String threadId
) {
}
