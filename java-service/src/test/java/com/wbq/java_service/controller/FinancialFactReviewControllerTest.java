package com.wbq.java_service.controller;

import java.util.UUID;

import com.wbq.java_service.auth.AuthUser;
import com.wbq.java_service.exception.BusinessException;
import com.wbq.java_service.identity.Role;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.SecurityContextHolder;

import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verifyNoInteractions;

class FinancialFactReviewControllerTest {

    private final JdbcTemplate jdbc = mock(JdbcTemplate.class);
    private final FinancialFactReviewController controller = new FinancialFactReviewController(jdbc);

    @AfterEach
    void clearAuth() {
        SecurityContextHolder.clearContext();
    }

    private static void login(Role role, String dept) {
        var user = new AuthUser(UUID.randomUUID(), "reviewer", "复核员", "", role, dept, "", true);
        SecurityContextHolder.getContext().setAuthentication(
                new UsernamePasswordAuthenticationToken(user, null, user.getAuthorities()));
    }

    @Test
    void queueRejectsUnknownDepartmentBeforeQueryingDatabase() {
        login(Role.ANALYST, "unknown");
        assertThrows(BusinessException.class, () -> controller.queue("pending", 0));
        verifyNoInteractions(jdbc);
    }

    @Test
    void rmCannotApproveFacts() {
        login(Role.RM, "rm");
        var request = new FinancialFactReviewController.ReviewRequest(
                "approve", "100.00", "已经核对原始年报和金额", "2026-10-08T12:00:00Z");
        assertThrows(BusinessException.class, () -> controller.review(1L, request));
        verifyNoInteractions(jdbc);
    }
}
