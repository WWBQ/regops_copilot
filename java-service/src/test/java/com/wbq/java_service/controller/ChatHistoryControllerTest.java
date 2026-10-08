package com.wbq.java_service.controller;

import java.util.List;
import java.util.UUID;

import com.wbq.java_service.auth.AuthUser;
import com.wbq.java_service.auth.JwtService;
import com.wbq.java_service.identity.Role;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
class ChatHistoryControllerTest {
    private static final UUID USER_ID = UUID.fromString("00000000-0000-0000-0000-000000000001");

    @Autowired MockMvc mvc;
    @MockitoBean JwtService jwtService;
    @MockitoBean JdbcTemplate jdbc;

    @Test
    void historyRequiresLogin() throws Exception {
        mvc.perform(get("/api/chat-history")).andExpect(status().isUnauthorized());
    }

    @Test
    void historyListIsScopedToJwtUser() throws Exception {
        when(jwtService.parse("valid")).thenReturn(new AuthUser(
                USER_ID, "analyst", "分析师", "", Role.ANALYST, "research", "", true));
        when(jdbc.query(anyString(), any(org.springframework.jdbc.core.RowMapper.class), eq(USER_ID)))
                .thenReturn(List.of());
        mvc.perform(get("/api/chat-history").header("Authorization", "Bearer valid"))
                .andExpect(status().isOk()).andExpect(content().json("[]"));
        verify(jdbc).query(anyString(), any(org.springframework.jdbc.core.RowMapper.class), eq(USER_ID));
    }
}
