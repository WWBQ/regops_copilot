package com.wbq.java_service.controller;

import java.util.List;
import java.util.Map;
import java.util.UUID;

import com.wbq.java_service.auth.AuthUser;
import com.wbq.java_service.auth.JwtService;
import com.wbq.java_service.client.RiskAgentClient;
import com.wbq.java_service.identity.Role;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
class CodingAgentControllerTest {
    private static final UUID USER_ID = UUID.fromString("00000000-0000-0000-0000-000000000001");

    @Autowired private MockMvc mvc;
    @MockitoBean private JwtService jwtService;
    @MockitoBean private RiskAgentClient client;

    @Test
    void codingRequiresAdmin() throws Exception {
        mvc.perform(get("/api/coding-agent/threads")).andExpect(status().isUnauthorized());
        authenticate(Role.ANALYST);
        mvc.perform(get("/api/coding-agent/threads").header("Authorization", "Bearer valid"))
                .andExpect(status().isForbidden());
    }

    @Test
    void adminGetsOnlyCodingNamespace() throws Exception {
        authenticate(Role.ADMIN);
        when(client.get("/regops/coding-agent/threads", USER_ID)).thenReturn(List.of());
        mvc.perform(get("/api/coding-agent/threads").header("Authorization", "Bearer valid"))
                .andExpect(status().isOk());
        verify(client).get("/regops/coding-agent/threads", USER_ID);

        when(client.get("/regops/coding-agent/projects", USER_ID))
                .thenReturn(Map.of("projects", List.of("demo")));
        mvc.perform(get("/api/coding-agent/projects").header("Authorization", "Bearer valid"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.projects[0]").value("demo"));
    }

    @Test
    void riskThreadCannotBeOpenedThroughCodingApi() throws Exception {
        authenticate(Role.ADMIN);
        String riskThread = USER_ID + "_11111111-1111-1111-1111-111111111111";
        mvc.perform(get("/api/coding-agent/threads/" + riskThread)
                        .header("Authorization", "Bearer valid"))
                .andExpect(status().isNotFound());
    }

    @Test
    void adminCanDownloadOnlyOwnedCodingSnapshot() throws Exception {
        authenticate(Role.ADMIN);
        String threadId = USER_ID + "_coding_11111111-1111-1111-1111-111111111111";
        String path = "/regops/coding-agent/threads/" + threadId + "/export";
        when(client.downloadArchive(path, USER_ID)).thenReturn(new byte[] {1, 2, 3});
        mvc.perform(get("/api/coding-agent/threads/" + threadId + "/export")
                        .header("Authorization", "Bearer valid"))
                .andExpect(status().isOk())
                .andExpect(content().bytes(new byte[] {1, 2, 3}));
        verify(client).downloadArchive(path, USER_ID);
    }

    private void authenticate(Role role) {
        when(jwtService.parse("valid")).thenReturn(new AuthUser(
                USER_ID, "tester", "Tester", "tester@example.test", role,
                "research", "", true
        ));
    }
}
