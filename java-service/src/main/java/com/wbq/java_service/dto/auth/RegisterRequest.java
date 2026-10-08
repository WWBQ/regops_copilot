package com.wbq.java_service.dto.auth;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record RegisterRequest(
        @NotBlank @Size(min = 3, max = 64) String username,
        @NotBlank @Size(min = 8, max = 72) String password,
        @NotBlank @Size(max = 80) String displayName,
        @Email @Size(max = 120) String email
) {}
