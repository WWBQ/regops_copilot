package com.wbq.java_service.controller;

import com.wbq.java_service.auth.AuthSupport;
import com.wbq.java_service.client.PythonAiClient;
import com.wbq.java_service.dto.chat.ChatRequest;
import com.wbq.java_service.dto.chat.ChatResponse;

import jakarta.servlet.http.HttpServletResponse;
import jakarta.validation.Valid;

import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.StreamingResponseBody;

@RestController
@RequestMapping("/api")
public class AiProxyController {

    private final PythonAiClient pythonAiClient;

    public AiProxyController(PythonAiClient pythonAiClient) {
        this.pythonAiClient = pythonAiClient;
    }

    @GetMapping("/models")
    public Object models() {
        return pythonAiClient.models();
    }

    @PostMapping("/chat")
    public ChatResponse chat(
            @Valid @RequestBody ChatRequest request,
            @RequestHeader(value = "X-Regops-Dept", required = false) String dept
    ) {
        return pythonAiClient.chat(request, AuthSupport.resolveDept(dept));
    }

    @PostMapping(value = "/chat/stream", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public StreamingResponseBody chatStream(
            @Valid @RequestBody ChatRequest request,
            @RequestHeader(value = "X-Regops-Dept", required = false) String dept,
            HttpServletResponse response
    ) {
        response.setBufferSize(64);
        response.setHeader(HttpHeaders.CACHE_CONTROL, "no-cache, no-transform");
        response.setHeader("X-Accel-Buffering", "no");
        response.setContentType(MediaType.TEXT_EVENT_STREAM_VALUE);
        String resolvedDept = AuthSupport.resolveDept(dept);
        String userId = AuthSupport.requireUser().publicId().toString();
        return output -> pythonAiClient.copyChatStream(request, output, resolvedDept, userId);
    }
}
