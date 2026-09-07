package com.wbq.java_service.dto.review;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record DecideRequest(
        @NotBlank @Size(max = 500) String reason
) {
}
