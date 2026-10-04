package com.wbq.java_service.controller;

import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.Map;
import java.util.UUID;

import com.wbq.java_service.auth.AuthSupport;
import com.wbq.java_service.client.RiskAgentClient;

import jakarta.servlet.http.HttpServletResponse;

import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.StreamingResponseBody;

@RestController
@RequestMapping("/api/risk-agent")
public class RiskAgentController {

    private final RiskAgentClient client;

    public RiskAgentController(RiskAgentClient client) {
        this.client = client;
    }

    @GetMapping("/health")
    public Object health() {
        Object upstream = client.get("/health", userId());
        if (!(upstream instanceof Map<?, ?> status) || !Boolean.TRUE.equals(status.get("ok"))) {
            throw new com.wbq.java_service.exception.PythonAiException(502, "Agent 后端未就绪", "upstream_down");
        }
        return Map.of("ok", true);
    }

    @GetMapping("/threads")
    public Object threads() {
        return client.get("/regops/agent/threads", userId());
    }

    @GetMapping("/options")
    public Object options() {
        return client.get("/regops/agent/options", userId());
    }

    @GetMapping("/threads/{threadId}")
    public Object thread(@PathVariable String threadId) {
        return client.get("/regops/agent/threads/" + checkedThreadId(threadId), userId());
    }

    @DeleteMapping("/threads/{threadId}")
    public void deleteThread(@PathVariable String threadId) {
        client.deleteThread(checkedThreadId(threadId), userId());
    }

    @PostMapping(value = "/threads/stream-message", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public StreamingResponseBody newMessage(@RequestBody Map<String, Object> body, HttpServletResponse response) {
        return stream(null, body, response);
    }

    @PostMapping(value = "/threads/{threadId}/stream-message", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public StreamingResponseBody nextMessage(
            @PathVariable String threadId,
            @RequestBody Map<String, Object> body,
            HttpServletResponse response) {
        return stream(checkedThreadId(threadId), body, response);
    }

    private StreamingResponseBody stream(String threadId, Map<String, Object> body, HttpServletResponse response) {
        Object raw = body.get("content");
        if (!(raw instanceof String content) || content.isBlank() || content.length() > 20_000) {
            throw new com.wbq.java_service.exception.PythonAiException(400, "请输入 1–20000 字的任务", "bad_request");
        }
        Object rawModel = body.get("model_id");
        if (rawModel != null && (!(rawModel instanceof String modelId) || modelId.isBlank())) {
            throw new com.wbq.java_service.exception.PythonAiException(400, "请选择有效的模型", "bad_request");
        }
        InputStream upstream = client.openStream(threadId, content, (String) rawModel, userId());
        response.setBufferSize(64);
        response.setHeader(HttpHeaders.CACHE_CONTROL, "no-cache, no-transform");
        response.setHeader("X-Accel-Buffering", "no");
        response.setCharacterEncoding(StandardCharsets.UTF_8.name());
        response.setContentType(MediaType.TEXT_EVENT_STREAM_VALUE);
        return output -> client.copyStream(upstream, output);
    }

    private UUID userId() {
        return AuthSupport.requireUser().publicId();
    }

    private String checkedThreadId(String threadId) {
        if (!threadId.matches("[0-9a-fA-F-]{36}_[0-9a-fA-F-]{36}")) {
            throw new com.wbq.java_service.exception.PythonAiException(404, "thread not found", "not_found");
        }
        return threadId;
    }
}
