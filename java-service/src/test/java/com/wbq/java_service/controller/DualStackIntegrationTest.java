package com.wbq.java_service.controller;

import com.wbq.java_service.client.PythonAiClient;
import com.wbq.java_service.dto.chat.ChatResponse;
import com.wbq.java_service.exception.PythonAiException;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.http.MediaType;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.ArgumentMatchers.nullable;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
class DualStackIntegrationTest {

    @Autowired
    private MockMvc mvc;

    @MockitoBean
    private PythonAiClient pythonAiClient;

    @Test
    void healthEchoesRequestIdAndStaysUpWhenPythonIsDown() throws Exception {
        when(pythonAiClient.health()).thenThrow(
                new PythonAiException(502, "python-ai unavailable", "upstream_down")
        );
        mvc.perform(get("/api/health").header("X-Request-ID", "e2e-health-1"))
                .andExpect(status().isOk())
                .andExpect(header().string("X-Request-ID", "e2e-health-1"))
                .andExpect(header().exists("traceparent"))
                .andExpect(jsonPath("$.status").value("ok"))
                .andExpect(jsonPath("$.service").value("java-service"))
                .andExpect(jsonPath("$.pythonAi.status").value("down"))
                .andExpect(jsonPath("$.pythonAi.error_code").value("upstream_down"));
    }

    @Test
    void chatTimeoutMapsTo504WithStableCode() throws Exception {
        when(pythonAiClient.chat(any(), nullable(String.class))).thenThrow(
                new PythonAiException(504, "python-ai timeout", "upstream_timeout")
        );
        mvc.perform(post("/api/chat")
                        .header("X-Request-ID", "e2e-timeout-1")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"message\":\"你好\",\"use_rag\":false}"))
                .andExpect(status().isGatewayTimeout())
                .andExpect(header().string("X-Request-ID", "e2e-timeout-1"))
                .andExpect(jsonPath("$.detail").value("python-ai timeout"))
                .andExpect(jsonPath("$.extra.error_code").value("upstream_timeout"))
                .andExpect(jsonPath("$.extra.request_id").value("e2e-timeout-1"));
    }

    @Test
    void chatUnavailableMapsTo502WithoutRawJson() throws Exception {
        when(pythonAiClient.chat(any(), nullable(String.class))).thenThrow(
                new PythonAiException(502, "python-ai unavailable", "upstream_down")
        );
        mvc.perform(post("/api/chat")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"message\":\"你好\",\"use_rag\":false}"))
                .andExpect(status().isBadGateway())
                .andExpect(jsonPath("$.detail").value("python-ai unavailable"))
                .andExpect(jsonPath("$.extra.error_code").value("upstream_down"))
                .andExpect(jsonPath("$.extra.request_id").exists());
    }

    @Test
    void chatSuccessStillWorks() throws Exception {
        when(pythonAiClient.chat(any(), nullable(String.class))).thenReturn(new ChatResponse(
                "hi",
                "deepseek",
                "disclaimer",
                java.util.List.of(),
                null,
                false,
                "chitchat",
                1,
                1,
                2,
                10.0,
                null
        ));
        mvc.perform(post("/api/chat")
                        .header("X-Request-ID", "e2e-chat-ok")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"message\":\"你好\",\"use_rag\":false}"))
                .andExpect(status().isOk())
                .andExpect(header().string("X-Request-ID", "e2e-chat-ok"))
                .andExpect(jsonPath("$.reply").value("hi"))
                .andExpect(jsonPath("$.total_latency_ms").value(10.0));
    }

    @Test
    void chatForwardsDeptHeader() throws Exception {
        when(pythonAiClient.chat(any(), eq("research"))).thenReturn(new ChatResponse(
                "hi",
                "deepseek",
                "disclaimer",
                java.util.List.of(),
                null,
                false,
                "chitchat",
                1,
                1,
                2,
                10.0,
                null
        ));
        mvc.perform(post("/api/chat")
                        .header("X-Regops-Dept", "research")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"message\":\"你好\",\"use_rag\":false}"))
                .andExpect(status().isOk());
        verify(pythonAiClient).chat(any(), eq("research"));
    }

    @Test
    void healthEchoesIncomingTraceparent() throws Exception {
        when(pythonAiClient.health()).thenThrow(
                new PythonAiException(502, "python-ai unavailable", "upstream_down")
        );
        String traceparent = "00-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa-bbbbbbbbbbbbbbbb-01";
        mvc.perform(get("/api/health").header("traceparent", traceparent))
                .andExpect(status().isOk())
                .andExpect(header().string("traceparent", traceparent));
    }
}
