package com.wbq.java_service.client;

import java.net.ConnectException;
import java.net.SocketTimeoutException;

import com.wbq.java_service.exception.PythonAiException;

import org.junit.jupiter.api.Test;
import org.springframework.web.client.ResourceAccessException;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class PythonErrorMapperTest {

    @Test
    void parsesFastapiStringDetail() {
        PythonAiException ex = PythonErrorMapper.fromDownstream(
                400,
                "{\"detail\":\"unsupported model: gpt-4\"}"
        );
        assertEquals(400, ex.getStatusCode());
        assertEquals("unsupported model: gpt-4", ex.getMessage());
        assertEquals("upstream_client_error", ex.getErrorCode());
    }

    @Test
    void parsesFastapiArrayDetail() {
        PythonAiException ex = PythonErrorMapper.fromDownstream(
                422,
                "{\"detail\":[{\"type\":\"string_too_short\",\"loc\":[\"body\",\"message\"],\"msg\":\"String should have at least 1 character\"}]}"
        );
        assertEquals(422, ex.getStatusCode());
        assertTrue(ex.getMessage().contains("at least 1 character"));
        assertFalse(ex.getMessage().startsWith("{"));
    }

    @Test
    void mapsReadTimeoutTo504() {
        Exception wrapped = new ResourceAccessException("I/O error", new SocketTimeoutException("Read timed out"));
        PythonAiException ex = PythonErrorMapper.fromTransport(wrapped);
        assertEquals(504, ex.getStatusCode());
        assertEquals("upstream_timeout", ex.getErrorCode());
        assertEquals("python-ai timeout", ex.getMessage());
    }

    @Test
    void mapsConnectionRefusedTo502() {
        Exception wrapped = new ResourceAccessException("I/O error", new ConnectException("Connection refused"));
        PythonAiException ex = PythonErrorMapper.fromTransport(wrapped);
        assertEquals(502, ex.getStatusCode());
        assertEquals("upstream_down", ex.getErrorCode());
        assertEquals("python-ai unavailable", ex.getMessage());
    }
}
