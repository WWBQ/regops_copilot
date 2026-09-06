package com.wbq.java_service.controller;

import java.util.Map;

import com.wbq.java_service.client.PythonAiClient;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/ops")
public class OpsProxyController {

    private final PythonAiClient pythonAiClient;

    public OpsProxyController(PythonAiClient pythonAiClient) {
        this.pythonAiClient = pythonAiClient;
    }

    @GetMapping("/rag/overview")
    public Map<String, Object> ragOverview() {
        return pythonAiClient.getRagOverview();
    }

    @GetMapping("/rag-traces")
    public Map<String, Object> listRagTraces(
            @RequestParam(defaultValue = "50") int limit,
            @RequestParam(defaultValue = "0") int offset,
            @RequestParam(required = false) String outcome
    ) {
        return pythonAiClient.listRagTraces(limit, offset, outcome);
    }

    @GetMapping("/rag-traces/{traceId}")
    public Map<String, Object> getRagTrace(@PathVariable int traceId) {
        return pythonAiClient.getRagTrace(traceId);
    }

    @GetMapping("/asknum-traces")
    public Map<String, Object> listAsknumTraces(
            @RequestParam(defaultValue = "50") int limit,
            @RequestParam(defaultValue = "0") int offset,
            @RequestParam(required = false) String route
    ) {
        return pythonAiClient.listAsknumTraces(limit, offset, route);
    }

    @GetMapping("/asknum-traces/{traceId}")
    public Map<String, Object> getAsknumTrace(@PathVariable int traceId) {
        return pythonAiClient.getAsknumTrace(traceId);
    }

    @GetMapping("/system/overview")
    public Map<String, Object> systemOverview() {
        return pythonAiClient.getSystemOverview();
    }

    @GetMapping("/ingest/overview")
    public Map<String, Object> ingestOverview() {
        return pythonAiClient.getIngestOverview();
    }

    @GetMapping("/ingest/jobs")
    public Map<String, Object> listIngestJobs(
            @RequestParam(defaultValue = "50") int limit,
            @RequestParam(defaultValue = "0") int offset,
            @RequestParam(required = false) String status,
            @RequestParam(value = "target_type", required = false) String targetType
    ) {
        return pythonAiClient.listIngestJobs(limit, offset, status, targetType);
    }

    @GetMapping("/ingest/session-documents")
    public Map<String, Object> listSessionIngestDocuments(
            @RequestParam(defaultValue = "30") int limit,
            @RequestParam(defaultValue = "0") int offset,
            @RequestParam(required = false) String status
    ) {
        return pythonAiClient.listSessionIngestDocuments(limit, offset, status);
    }

    @GetMapping("/logs/events")
    public Map<String, Object> listLogEvents(
            @RequestParam(defaultValue = "50") int limit,
            @RequestParam(defaultValue = "0") int offset,
            @RequestParam(required = false) String source,
            @RequestParam(required = false) String level
    ) {
        return pythonAiClient.listLogEvents(limit, offset, source, level);
    }

    @GetMapping("/quality/gates")
    public Map<String, Object> qualityGates() {
        return pythonAiClient.getQualityGates();
    }

    @GetMapping("/quality/facts")
    public Map<String, Object> qualityFacts(
            @RequestParam(defaultValue = "200") int limit,
            @RequestParam(defaultValue = "0") int offset,
            @RequestParam(value = "company_code", required = false) String companyCode,
            @RequestParam(required = false) String status,
            @RequestParam(required = false) String statement,
            @RequestParam(required = false) String concept,
            @RequestParam(value = "doc_id", required = false) String docId
    ) {
        return pythonAiClient.listQualityFacts(limit, offset, companyCode, status, statement, concept, docId);
    }

    @PostMapping("/quality/ingest")
    public Map<String, Object> qualityIngest(@RequestBody Map<String, Object> body) {
        return pythonAiClient.ingestQualityFacts(body);
    }
}
