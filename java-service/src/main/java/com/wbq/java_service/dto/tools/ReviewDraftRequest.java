package com.wbq.java_service.dto.tools;

import com.fasterxml.jackson.annotation.JsonProperty;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

public record ReviewDraftRequest(
        @NotBlank
        @Pattern(regexp = "\\d{6}", message = "company_code 必须是 6 位证券代码")
        @JsonProperty("company_code")
        String companyCode,
        @NotBlank @Size(max = 120) String title,
        @NotBlank @Size(max = 500) String reason
) {
}
