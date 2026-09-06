package com.wbq.java_service.dto.tools;

import com.fasterxml.jackson.annotation.JsonProperty;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;

public record ScopeToolRequest(
        @JsonProperty("company_code") String companyCode,
        @Min(2000) @Max(2100) Integer year,
        String scope,
        String backend
) {
}
