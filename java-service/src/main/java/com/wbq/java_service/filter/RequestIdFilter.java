package com.wbq.java_service.filter;

import java.io.IOException;
import java.security.SecureRandom;
import java.util.Locale;
import java.util.UUID;
import java.util.regex.Pattern;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.slf4j.MDC;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

@Component
@Order(Ordered.HIGHEST_PRECEDENCE)
public class RequestIdFilter extends OncePerRequestFilter {

    public static final String HEADER = "X-Request-ID";
    public static final String TRACEPARENT_HEADER = "traceparent";
    public static final String MDC_KEY = "requestId";
    public static final String TRACE_MDC_KEY = "traceId";
    public static final String TRACEPARENT_MDC_KEY = "traceparent";

    private static final Pattern TRACEPARENT = Pattern.compile(
            "^00-[0-9a-f]{32}-[0-9a-f]{16}-[0-9a-f]{2}$"
    );
    private static final SecureRandom RANDOM = new SecureRandom();

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain
    ) throws ServletException, IOException {
        String requestId = request.getHeader(HEADER);
        if (requestId == null || requestId.isBlank()) {
            requestId = UUID.randomUUID().toString();
        }
        String traceparent = normalizeTraceparent(request.getHeader(TRACEPARENT_HEADER));
        String traceId = traceparent.split("-")[1];
        MDC.put(MDC_KEY, requestId);
        MDC.put(TRACE_MDC_KEY, traceId);
        MDC.put(TRACEPARENT_MDC_KEY, traceparent);
        response.setHeader(HEADER, requestId);
        response.setHeader(TRACEPARENT_HEADER, traceparent);
        try {
            filterChain.doFilter(request, response);
        } finally {
            MDC.remove(MDC_KEY);
            MDC.remove(TRACE_MDC_KEY);
            MDC.remove(TRACEPARENT_MDC_KEY);
        }
    }

    static String normalizeTraceparent(String incoming) {
        if (incoming != null && !incoming.isBlank()) {
            String lower = incoming.trim().toLowerCase(Locale.ROOT);
            if (TRACEPARENT.matcher(lower).matches()
                    && !lower.contains("00000000000000000000000000000000")
                    && !lower.contains("-0000000000000000-")) {
                return lower;
            }
        }
        return mintTraceparent();
    }

    static String mintTraceparent() {
        return "00-" + randomHex(16) + "-" + randomHex(8) + "-01";
    }

    private static String randomHex(int bytes) {
        byte[] buf = new byte[bytes];
        RANDOM.nextBytes(buf);
        StringBuilder out = new StringBuilder(bytes * 2);
        for (byte item : buf) {
            out.append(String.format(Locale.ROOT, "%02x", item));
        }
        return out.toString();
    }
}
