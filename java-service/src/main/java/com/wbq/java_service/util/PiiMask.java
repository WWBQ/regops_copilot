package com.wbq.java_service.util;

import java.util.regex.Pattern;

/** 日志脱敏：身份证、手机号、账号。 */
public final class PiiMask {

    private static final Pattern ID_CARD = Pattern.compile("\\b\\d{17}[\\dXx]\\b");
    private static final Pattern PHONE = Pattern.compile("\\b1[3-9]\\d{9}\\b");
    private static final Pattern ACCOUNT = Pattern.compile("\\b\\d{12,19}\\b");

    private PiiMask() {
    }

    public static String mask(String text) {
        if (text == null || text.isBlank()) {
            return text;
        }
        String masked = ID_CARD.matcher(text).replaceAll("[身份证]");
        masked = PHONE.matcher(masked).replaceAll("[手机号]");
        return ACCOUNT.matcher(masked).replaceAll("[账号]");
    }
}
