package com.wbq.java_service.controller;

import java.util.Map;

import com.wbq.java_service.client.PythonAiClient;
import com.wbq.java_service.dto.common.ServiceHealthResponse;
import com.wbq.java_service.exception.PythonAiException;

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
            if (ex instanceof PythonAiException py) {
                pythonHealth = Map.of(
                        "status", "down",
                        "error", py.getMessage(),
                        "error_code", py.getErrorCode()
                );
            } else {
                pythonHealth = Map.of(
                        "status", "down",
                        "error", "unavailable",
                        "error_code", "upstream_down"
                );
            }
        }
        return new ServiceHealthResponse("ok", "java-service", pythonHealth);
    }
}
