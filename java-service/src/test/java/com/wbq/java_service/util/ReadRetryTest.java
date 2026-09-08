package com.wbq.java_service.util;

import java.util.concurrent.atomic.AtomicInteger;

import com.wbq.java_service.exception.PythonAiException;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class ReadRetryTest {

    @Test
    void retriesOn502ThenSucceeds() {
        AtomicInteger attempts = new AtomicInteger();
        String out = ReadRetry.call(2, () -> {
            if (attempts.incrementAndGet() < 3) {
                throw new PythonAiException(502, "down");
            }
            return "ok";
        });
        assertEquals("ok", out);
        assertEquals(3, attempts.get());
    }

    @Test
    void doesNotRetryOn504Timeout() {
        AtomicInteger attempts = new AtomicInteger();
        assertThrows(PythonAiException.class, () -> ReadRetry.call(2, () -> {
            attempts.incrementAndGet();
            throw new PythonAiException(504, "python-ai timeout", "upstream_timeout");
        }));
        assertEquals(1, attempts.get());
    }
}
