package com.wbq.java_service.monitoring;

import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.NavigableMap;
import java.util.TreeMap;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.stereotype.Component;

/** BFF HTTP 请求计数；只保存最近 15 分钟的分钟桶，不保存请求内容或用户信息。 */
@Component
public class SystemRequestMetrics {

    private static final int HISTORY_MINUTES = 15;
    private final NavigableMap<Long, MinuteBucket> minutes = new TreeMap<>();
    private final AtomicInteger inFlight = new AtomicInteger();
    private long totalSinceStart;

    public void started() {
        inFlight.incrementAndGet();
    }

    public void finished(int status, long latencyMs) {
        inFlight.decrementAndGet();
        record(status, latencyMs);
    }

    synchronized void record(int status, long latencyMs) {
        long minute = System.currentTimeMillis() / 60_000;
        totalSinceStart++;
        MinuteBucket bucket = minutes.computeIfAbsent(minute, ignored -> new MinuteBucket());
        bucket.count++;
        bucket.latencyMs += Math.max(0, latencyMs);
        if (status >= 500) bucket.errors++;
        prune(minute);
    }

    public synchronized Map<String, Object> snapshot() {
        long currentMinute = System.currentTimeMillis() / 60_000;
        prune(currentMinute);
        List<Map<String, Object>> series = new ArrayList<>();
        long lastFiveCount = 0;
        long lastFiveErrors = 0;
        long lastFiveLatency = 0;
        for (long minute = currentMinute - HISTORY_MINUTES + 1; minute <= currentMinute; minute++) {
            MinuteBucket bucket = minutes.get(minute);
            long count = bucket == null ? 0 : bucket.count;
            long errors = bucket == null ? 0 : bucket.errors;
            series.add(Map.of(
                    "at", Instant.ofEpochMilli(minute * 60_000).toString(),
                    "count", count,
                    "error_count", errors
            ));
            if (minute >= currentMinute - 4) {
                lastFiveCount += count;
                lastFiveErrors += errors;
                lastFiveLatency += bucket == null ? 0 : bucket.latencyMs;
            }
        }
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("total_since_start", totalSinceStart);
        result.put("last_5m", lastFiveCount);
        result.put("errors_5m", lastFiveErrors);
        result.put("error_rate_5m", lastFiveCount == 0 ? 0.0 : (double) lastFiveErrors / lastFiveCount);
        result.put("avg_latency_ms_5m", lastFiveCount == 0 ? null : Math.round((double) lastFiveLatency / lastFiveCount * 10.0) / 10.0);
        result.put("in_flight", inFlight.get());
        result.put("per_minute", series);
        return result;
    }

    private void prune(long currentMinute) {
        minutes.headMap(currentMinute - HISTORY_MINUTES + 1, false).clear();
    }

    private static final class MinuteBucket {
        private long count;
        private long errors;
        private long latencyMs;
    }
}
