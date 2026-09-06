package com.wbq.java_service.util;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class PiiMaskTest {

    @Test
    void masksIdPhoneAndAccount() {
        String masked = PiiMask.mask("联系 13812345678 身份证 110101199001011234 账号 6222021234567890123");
        assertFalse(masked.contains("13812345678"));
        assertFalse(masked.contains("110101199001011234"));
        assertTrue(masked.contains("[手机号]"));
        assertTrue(masked.contains("[身份证]"));
        assertTrue(masked.contains("[账号]"));
    }
}
