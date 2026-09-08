package com.wbq.java_service.util;

import java.util.regex.Pattern;

/** 日志脱敏：身份证、手机号、账号、API Key。 */
public final class PiiMask {

    private static final Pattern ID_CARD = Pattern.compile("\\b\\d{17}[\\dXx]\\b");
    private static final Pattern PHONE = Pattern.compile("\\b1[3-9]\\d{9}\\b");
    private static final Pattern ACCOUNT = Pattern.compile("\\b\\d{12,19}\\b");
    private static final Pattern API_KEY = Pattern.compile(
            "(?i)\\b(?:sk-[A-Za-z0-9]{8,}|Bearer\\s+[A-Za-z0-9._\\-+=/]{8,})\\b"
    );
    private static final Pattern ENV_SECRET = Pattern.compile(
            "(?i)\\b(?:DEEPSEEK_API_KEY|QWEN_API_KEY|REGOPS_JWT_SECRET|REGOPS_SERVICE_TOKEN"
                    + "|LANGFUSE_SECRET_KEY|LANGFUSE_PUBLIC_KEY)\\s*[=:]\\s*\\S+"
    );

    private PiiMask() {
    }

    public static String mask(String text) {
        if (text == null || text.isBlank()) {
            return text;
        }
        String masked = ID_CARD.matcher(text).replaceAll("[身份证]");
        masked = PHONE.matcher(masked).replaceAll("[手机号]");
        masked = ACCOUNT.matcher(masked).replaceAll("[账号]");
        masked = API_KEY.matcher(masked).replaceAll("[密钥]");
        return ENV_SECRET.matcher(masked).replaceAll("[密钥]");
    }
}
