package com.wbq.java_service.controller;

import java.io.ByteArrayInputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Map;
import java.util.UUID;

import com.wbq.java_service.auth.AuthUser;
import com.wbq.java_service.auth.JwtService;
import com.wbq.java_service.client.RiskAgentClient;
import com.wbq.java_service.exception.PythonAiException;
import com.wbq.java_service.identity.Role;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.http.MediaType;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.doAnswer;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.asyncDispatch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.request;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
class RiskAgentControllerTest {

    private static final UUID USER_ID = UUID.fromString("00000000-0000-0000-0000-000000000001");

    @Autowired
    private MockMvc mvc;

    @MockitoBean
    private JwtService jwtService;

    @MockitoBean
    private RiskAgentClient client;

    @Test
    void anonymousCannotReadThreads() throws Exception {
        mvc.perform(get("/api/risk-agent/threads"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void forwardsCurrentUserIdentityToAgent() throws Exception {
        authenticate();
        when(client.get("/regops/agent/threads", USER_ID)).thenReturn(List.of());
        mvc.perform(get("/api/risk-agent/threads").header("Authorization", "Bearer valid"))
                .andExpect(status().isOk())
                .andExpect(content().json("[]"));
        verify(client).get("/regops/agent/threads", USER_ID);
    }

    @Test
    void healthDoesNotExposeAgentFilesystemPaths() throws Exception {
        authenticate();
        when(client.get("/health", USER_ID)).thenReturn(Map.of("ok", true, "project_root", "/private/app"));
        mvc.perform(get("/api/risk-agent/health").header("Authorization", "Bearer valid"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.ok").value(true))
                .andExpect(jsonPath("$.project_root").doesNotExist());
    }

    @Test
    void listsAvailableAgentModels() throws Exception {
        authenticate();
        when(client.get("/regops/agent/options", USER_ID))
                .thenReturn(Map.of("models", List.of(Map.of("id", "qwen3.8-max")), "default_agent_model", "qwen3.8-max"));
        mvc.perform(get("/api/risk-agent/options").header("Authorization", "Bearer valid"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.models[0].id").value("qwen3.8-max"));
    }

    @Test
    void relaysNamedSseEvents() throws Exception {
        authenticate();
        String sse = "event: text_delta\ndata: {\"content\":\"风险线索\"}\n\n";
        when(client.openStream(eq(null), eq("检查风险"), eq("qwen3.8-max"), eq(USER_ID)))
                .thenReturn(new ByteArrayInputStream(sse.getBytes(StandardCharsets.UTF_8)));
        doAnswer(invocation -> {
            InputStream in = invocation.getArgument(0);
            OutputStream out = invocation.getArgument(1);
            in.transferTo(out);
            return null;
        }).when(client).copyStream(any(), any());
        MvcResult result = mvc.perform(post("/api/risk-agent/threads/stream-message")
                        .header("Authorization", "Bearer valid")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"content\":\"检查风险\",\"model_id\":\"qwen3.8-max\"}"))
                .andExpect(request().asyncStarted())
                .andReturn();
        mvc.perform(asyncDispatch(result))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(MediaType.TEXT_EVENT_STREAM))
                .andExpect(content().string(sse));
    }

    @Test
    void streamSetupFailureKeepsUpstreamStatusAsJson() throws Exception {
        authenticate();
        when(client.openStream(eq(null), eq("检查风险"), eq("qwen3.8-max"), eq(USER_ID)))
                .thenThrow(new PythonAiException(503, "财务 MCP 服务不可用", "upstream_down"));

        mvc.perform(post("/api/risk-agent/threads/stream-message")
                        .header("Authorization", "Bearer valid")
                        .accept(MediaType.TEXT_EVENT_STREAM, MediaType.APPLICATION_JSON)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"content\":\"检查风险\",\"model_id\":\"qwen3.8-max\"}"))
                .andExpect(status().isServiceUnavailable())
                .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
                .andExpect(jsonPath("$.detail").value("财务 MCP 服务不可用"));
    }

    private void authenticate() {
        when(jwtService.parse("valid")).thenReturn(new AuthUser(
                USER_ID, "analyst", "Analyst", "analyst@example.test", Role.ANALYST,
                "research", "", true
        ));
    }
}
