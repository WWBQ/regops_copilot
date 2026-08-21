package com.wbq.java_service.controller;

import java.util.Map;

import com.wbq.java_service.client.PythonAiClient;
import com.wbq.java_service.dto.common.ServiceHealthResponse;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class HealthController {

    private final PythonAiClient pythonAiClient;

    public HealthController(PythonAiClient pythonAiClient) {
        this.pythonAiClient = pythonAiClient;
    }

    @GetMapping("/health")
    public ServiceHealthResponse health() {
        Map<String, Object> pythonHealth;
        try {
            pythonHealth = pythonAiClient.health();
        } catch (Exception ex) {
            pythonHealth = Map.of(
                    "status", "down",
                    "error", ex.getMessage()
            );
        }
        return new ServiceHealthResponse("ok", "java-service", pythonHealth);
    }
}
