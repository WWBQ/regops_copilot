package com.wbq.java_service.monitoring;

import java.lang.management.ManagementFactory;
import java.lang.management.MemoryUsage;
import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.Map;

import com.wbq.java_service.client.PythonAiClient;

import org.springframework.stereotype.Service;

@Service
public class SystemHealthService {

    private final SystemRequestMetrics requestMetrics;
    private final PythonAiClient pythonAiClient;

    public SystemHealthService(SystemRequestMetrics requestMetrics, PythonAiClient pythonAiClient) {
        this.requestMetrics = requestMetrics;
        this.pythonAiClient = pythonAiClient;
    }

    public Map<String, Object> overview() {
        Map<String, Object> services = new LinkedHashMap<>();
        services.put("java_bff", Map.of("status", "ok", "service", "java-service"));
        try {
            Map<String, Object> upstream = pythonAiClient.getSystemOverview();
            Object upstreamServices = upstream.get("services");
            if (upstreamServices instanceof Map<?, ?> serviceMap) {
                for (String name : new String[]{"python_ai", "postgresql", "pgvector", "redis", "rabbitmq"}) {
                    Object service = serviceMap.get(name);
                    services.put(name, service == null ? Map.of("status", "unknown") : service);
                }
            } else {
                services.put("python_ai", Map.of("status", "unknown"));
            }
        } catch (Exception ex) {
            services.put("python_ai", Map.of("status", "down"));
            services.put("postgresql", Map.of("status", "unknown"));
            services.put("pgvector", Map.of("status", "unknown"));
            services.put("redis", Map.of("status", "unknown"));
            services.put("rabbitmq", Map.of("status", "unknown"));
        }

        MemoryUsage heap = ManagementFactory.getMemoryMXBean().getHeapMemoryUsage();
        long heapMax = heap.getMax();
        Double cpuPercent = null;
        var os = ManagementFactory.getOperatingSystemMXBean();
        if (os instanceof com.sun.management.OperatingSystemMXBean extended) {
            double load = extended.getProcessCpuLoad();
            if (load >= 0) cpuPercent = Math.round(load * 1000.0) / 10.0;
        }
        Map<String, Object> pressure = new LinkedHashMap<>();
        pressure.put("cpu_percent", cpuPercent);
        pressure.put("heap_used_bytes", heap.getUsed());
        pressure.put("heap_max_bytes", heapMax > 0 ? heapMax : null);
        pressure.put("heap_usage_percent", heapMax > 0 ? Math.round((double) heap.getUsed() / heapMax * 1000.0) / 10.0 : null);
        pressure.put("thread_count", ManagementFactory.getThreadMXBean().getThreadCount());
        pressure.put("available_processors", Runtime.getRuntime().availableProcessors());
        double loadAverage = os.getSystemLoadAverage();
        pressure.put("load_average_1m", loadAverage >= 0 ? Math.round(loadAverage * 100.0) / 100.0 : null);

        return Map.of(
                "checked_at", Instant.now().toString(),
                "uptime_seconds", ManagementFactory.getRuntimeMXBean().getUptime() / 1000,
                "services", services,
                "requests", requestMetrics.snapshot(),
                "pressure", pressure
        );
    }
}
