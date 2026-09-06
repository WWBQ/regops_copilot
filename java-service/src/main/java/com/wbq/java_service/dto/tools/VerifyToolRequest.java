package com.wbq.java_service.dto.tools;

import com.fasterxml.jackson.annotation.JsonProperty;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

public record VerifyToolRequest(
        @NotBlank
        @Pattern(regexp = "\\d{6}", message = "company_code 必须是 6 位证券代码")
        @JsonProperty("company_code")
        String companyCode,
        @NotBlank String concept,
        @Min(2000) @Max(2100) int year,
        String scope,
        @NotBlank @Size(max = 64) String claimed,
        String backend
) {
    public String scopeOrDefault() {
        return scope == null || scope.isBlank() ? "consolidated" : scope;
    }
}
