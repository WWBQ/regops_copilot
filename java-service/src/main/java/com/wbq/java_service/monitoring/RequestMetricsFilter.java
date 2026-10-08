package com.wbq.java_service.monitoring;

import java.io.IOException;
import java.util.concurrent.atomic.AtomicBoolean;

import jakarta.servlet.AsyncEvent;
import jakarta.servlet.AsyncListener;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

/** 覆盖 BFF API（包括认证失败），排除探活和监控轮询，避免统计自增。 */
@Component
@Order(Ordered.HIGHEST_PRECEDENCE)
public class RequestMetricsFilter extends OncePerRequestFilter {

    private final SystemRequestMetrics metrics;

    public RequestMetricsFilter(SystemRequestMetrics metrics) {
        this.metrics = metrics;
    }

    @Override
    protected boolean shouldNotFilter(HttpServletRequest request) {
        String path = request.getRequestURI();
        return !path.startsWith("/api/")
                || path.equals("/api/health")
                || path.equals("/api/ops/system/overview");
    }

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response, FilterChain chain)
            throws ServletException, IOException {
        long startedAt = System.nanoTime();
        AtomicBoolean completed = new AtomicBoolean();
        metrics.started();
        try {
            chain.doFilter(request, response);
        } catch (ServletException | IOException | RuntimeException ex) {
            finish(completed, response, startedAt, 500);
            throw ex;
        } finally {
            if (request.isAsyncStarted() && !completed.get()) {
                try {
                    request.getAsyncContext().addListener(new AsyncListener() {
                        @Override
                        public void onComplete(AsyncEvent event) {
                            finish(completed, response, startedAt, response.getStatus());
                        }

                        @Override
                        public void onTimeout(AsyncEvent event) {
                            finish(completed, response, startedAt, 504);
                        }

                        @Override
                        public void onError(AsyncEvent event) {
                            finish(completed, response, startedAt, 500);
                        }

                        @Override
                        public void onStartAsync(AsyncEvent event) {
                            event.getAsyncContext().addListener(this);
                        }
                    });
                } catch (IllegalStateException ex) {
                    finish(completed, response, startedAt, response.getStatus());
                }
            } else {
                finish(completed, response, startedAt, response.getStatus());
            }
        }
    }

    private void finish(AtomicBoolean completed, HttpServletResponse response, long startedAt, int status) {
        if (completed.compareAndSet(false, true)) {
            long durationMs = (System.nanoTime() - startedAt) / 1_000_000;
            metrics.finished(status, durationMs);
        }
    }
}
