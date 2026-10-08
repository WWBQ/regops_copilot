package com.wbq.java_service.controller;

import java.util.List;
import java.util.Map;
import java.util.UUID;

import com.wbq.java_service.auth.AuthUser;
import com.wbq.java_service.client.PythonAiClient;
import com.wbq.java_service.identity.Role;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.SecurityContextHolder;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import com.wbq.java_service.exception.BusinessException;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class DocumentProxyControllerTest {

    @AfterEach
    void clearAuth() {
        SecurityContextHolder.clearContext();
    }

    @Test
    void annualReportsOnlyListsCurrentDepartmentsCompanies() {
        var user = new AuthUser(UUID.randomUUID(), "analyst", "分析师", "", Role.ANALYST, "research", "", true);
        SecurityContextHolder.getContext().setAuthentication(
                new UsernamePasswordAuthenticationToken(user, null, user.getAuthorities()));
        var client = mock(PythonAiClient.class);
        when(client.listAnnualReports()).thenReturn(Map.of("items", List.of(
                Map.of("doc_id", "002594_2024", "company_code", "002594"),
                Map.of("doc_id", "000333_2024", "company_code", "000333"))));

        var response = new DocumentProxyController(client).annualReports();

        assertEquals(List.of(Map.of("doc_id", "002594_2024", "company_code", "002594")), response.get("items"));
        assertThrows(BusinessException.class,
                () -> new DocumentProxyController(client).documentContent("000333_2024"));
    }
}
