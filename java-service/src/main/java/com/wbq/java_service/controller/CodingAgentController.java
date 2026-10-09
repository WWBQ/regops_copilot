package com.wbq.java_service.controller;

import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.Map;
import java.util.UUID;

import com.wbq.java_service.auth.AuthSupport;
import com.wbq.java_service.client.RiskAgentClient;
import com.wbq.java_service.exception.PythonAiException;

import jakarta.servlet.http.HttpServletResponse;

import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.StreamingResponseBody;

/** AI Coding executes commands in the configured workspace; only admins may use it. */
@RestController
@RequestMapping("/api/coding-agent")
@PreAuthorize("hasRole('ADMIN')")
public class CodingAgentController {

    private static final String UPSTREAM = "/regops/coding-agent";
    private final RiskAgentClient client;

    public CodingAgentController(RiskAgentClient client) {
        this.client = client;
    }

    @GetMapping("/health")
    public Object health() {
        Object upstream = client.get("/health", userId());
        if (!(upstream instanceof Map<?, ?> status) || !Boolean.TRUE.equals(status.get("ok"))) {
            throw new PythonAiException(502, "AI Coding 后端未就绪", "upstream_down");
        }
        return Map.of("ok", true);
    }

    @GetMapping("/options")
    public Object options() {
        return client.get(UPSTREAM + "/options", userId());
    }

    @GetMapping("/projects")
    public Object projects() {
        return client.get(UPSTREAM + "/projects", userId());
    }

    @GetMapping("/threads")
    public Object threads() {
        return client.get(UPSTREAM + "/threads", userId());
    }

    @GetMapping("/threads/{threadId}")
    public Object thread(@PathVariable String threadId) {
        return client.get(UPSTREAM + "/threads/" + checkedThreadId(threadId), userId());
    }

    @GetMapping(value = "/threads/{threadId}/export", produces = "application/zip")
    public ResponseEntity<byte[]> exportThread(@PathVariable String threadId) {
        byte[] archive = client.downloadArchive(
                UPSTREAM + "/threads/" + checkedThreadId(threadId) + "/export", userId());
        return ResponseEntity.ok()
                .header(HttpHeaders.CONTENT_DISPOSITION, "attachment; filename=ai-coding-sandbox.zip")
                .header(HttpHeaders.CACHE_CONTROL, "no-store")
                .contentType(MediaType.parseMediaType("application/zip"))
                .body(archive);
    }

    @DeleteMapping("/threads/{threadId}")
    public void deleteThread(@PathVariable String threadId) {
        client.deleteThread(UPSTREAM, checkedThreadId(threadId), userId());
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
            throw new PythonAiException(400, "请输入 1–20000 字的任务", "bad_request");
        }
        Object rawModel = body.get("model_id");
        if (rawModel != null && (!(rawModel instanceof String modelId) || modelId.isBlank())) {
            throw new PythonAiException(400, "请选择有效的模型", "bad_request");
        }
        InputStream upstream = client.openStream(UPSTREAM, threadId, content, (String) rawModel, userId());
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
        if (!threadId.matches("[0-9a-fA-F-]{36}_coding_[0-9a-fA-F-]{36}")) {
            throw new PythonAiException(404, "thread not found", "not_found");
        }
        return threadId;
    }
}
