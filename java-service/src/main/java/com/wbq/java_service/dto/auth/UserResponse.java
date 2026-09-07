package com.wbq.java_service.dto.auth;

public record UserResponse(
        String id,
        String username,
        String displayName,
        String email,
        String role,
        String dept
) {
}
