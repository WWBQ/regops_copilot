package com.wbq.java_service;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

import com.wbq.java_service.client.PythonAiClient;

@SpringBootTest
@ActiveProfiles("test")
class JavaServiceApplicationTests {

    @MockitoBean
    private PythonAiClient pythonAiClient;

    @Test
    void contextLoads() {
    }
}
