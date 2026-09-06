package com.wbq.java_service.dto.tools;

import java.util.List;

import com.fasterxml.jackson.annotation.JsonProperty;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.Size;

public record CompareToolRequest(
        @NotEmpty
        @Size(min = 2, max = 5, message = "company_codes 需要 2–5 家")
        @JsonProperty("company_codes")
        List<String> companyCodes,
        @NotBlank String concept,
        @Min(2000) @Max(2100) int year,
        String scope,
        String backend
) {
    public String scopeOrDefault() {
        return scope == null || scope.isBlank() ? "consolidated" : scope;
    }
}
