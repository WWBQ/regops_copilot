package com.wbq.java_service.controller;

import com.wbq.java_service.client.PythonAiClient;
import com.wbq.java_service.dto.chat.ChatRequest;
import com.wbq.java_service.dto.chat.ChatResponse;

import jakarta.validation.Valid;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

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
    public ChatResponse chat(@Valid @RequestBody ChatRequest request) {
        return pythonAiClient.chat(request);
    }
}
