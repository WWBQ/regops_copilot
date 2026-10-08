package com.wbq.java_service.monitoring;

import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockFilterChain;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;

import static org.junit.jupiter.api.Assertions.assertEquals;

class SystemRequestMetricsTest {

    @Test
    void countsRequestsErrorsLatencyAndInFlight() {
        SystemRequestMetrics metrics = new SystemRequestMetrics();
        metrics.started();
        metrics.started();
        assertEquals(2, metrics.snapshot().get("in_flight"));

        metrics.finished(200, 100);
        metrics.finished(503, 300);
        Map<String, Object> result = metrics.snapshot();

        assertEquals(2L, result.get("total_since_start"));
        assertEquals(2L, result.get("last_5m"));
        assertEquals(1L, result.get("errors_5m"));
        assertEquals(0.5, result.get("error_rate_5m"));
        assertEquals(200.0, result.get("avg_latency_ms_5m"));
        assertEquals(0, result.get("in_flight"));
        assertEquals(15, ((List<?>) result.get("per_minute")).size());
    }

    @Test
    void filterTracksApiRequestsButNotHealthPolling() throws Exception {
        SystemRequestMetrics metrics = new SystemRequestMetrics();
        RequestMetricsFilter filter = new RequestMetricsFilter(metrics);
        MockHttpServletRequest apiRequest = new MockHttpServletRequest("GET", "/api/chat");
        MockHttpServletResponse apiResponse = new MockHttpServletResponse();
        filter.doFilter(apiRequest, apiResponse, (request, response) ->
                ((MockHttpServletResponse) response).setStatus(503));

        MockHttpServletRequest healthRequest = new MockHttpServletRequest("GET", "/api/ops/system/overview");
        filter.doFilter(healthRequest, new MockHttpServletResponse(), new MockFilterChain());

        assertEquals(1L, metrics.snapshot().get("total_since_start"));
        assertEquals(1L, metrics.snapshot().get("errors_5m"));
    }
}
