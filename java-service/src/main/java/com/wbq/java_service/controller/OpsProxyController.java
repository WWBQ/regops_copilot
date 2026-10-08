package com.wbq.java_service.controller;

import java.util.Map;
import java.util.List;

import com.wbq.java_service.client.PythonAiClient;
import com.wbq.java_service.auth.AuthSupport;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

@RestController
@RequestMapping("/api/ops")
public class OpsProxyController {

    private final PythonAiClient pythonAiClient;

    public OpsProxyController(PythonAiClient pythonAiClient) {
        this.pythonAiClient = pythonAiClient;
    }

    @GetMapping("/rag/overview")
    public Map<String, Object> ragOverview() {
        AuthSupport.requireUser();
        return pythonAiClient.getRagOverview();
    }

    @GetMapping("/rag-traces")
    public Map<String, Object> listRagTraces(
            @RequestParam(defaultValue = "50") int limit,
            @RequestParam(defaultValue = "0") int offset,
            @RequestParam(required = false) String outcome
    ) {
        AuthSupport.requireUser();
        return pythonAiClient.listRagTraces(limit, offset, outcome);
    }

    @GetMapping("/rag-traces/{traceId}")
    public Map<String, Object> getRagTrace(@PathVariable int traceId) {
        AuthSupport.requireUser();
        return pythonAiClient.getRagTrace(traceId);
    }

    @GetMapping("/asknum-traces")
    public Map<String, Object> listAsknumTraces(
            @RequestParam(defaultValue = "50") int limit,
            @RequestParam(defaultValue = "0") int offset,
            @RequestParam(required = false) String route
    ) {
        AuthSupport.requireUser();
        return pythonAiClient.listAsknumTraces(limit, offset, route);
    }

    @GetMapping("/asknum-traces/{traceId}")
    public Map<String, Object> getAsknumTrace(@PathVariable int traceId) {
        AuthSupport.requireUser();
        return pythonAiClient.getAsknumTrace(traceId);
    }

    @GetMapping("/system/overview")
    public Map<String, Object> systemOverview() {
        return pythonAiClient.getSystemOverview();
    }

    @GetMapping("/obs/overview")
    public Map<String, Object> obsOverview() {
        return pythonAiClient.getObsOverview();
    }

    @GetMapping("/obs/traces")
    public Map<String, Object> listObsTraces(
            @RequestParam(defaultValue = "50") int limit,
            @RequestParam(defaultValue = "0") int offset
    ) {
        return pythonAiClient.listObsTraces(limit, offset);
    }

    @GetMapping("/performance/overview")
    public Map<String, Object> performanceOverview() {
        return pythonAiClient.getPerformanceOverview();
    }

    @GetMapping("/performance-traces")
    public Map<String, Object> listPerformanceTraces(
            @RequestParam(defaultValue = "50") int limit,
            @RequestParam(defaultValue = "0") int offset
    ) {
        return pythonAiClient.listPerformanceTraces(limit, offset);
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

    @GetMapping("/ingest/batches")
    public Map<String, Object> listIngestBatches(
            @RequestParam(defaultValue = "20") int limit,
            @RequestParam(defaultValue = "0") int offset,
            @RequestParam(required = false) String status,
            @RequestParam(value = "parser_backend", required = false) String parserBackend,
            @RequestParam(required = false) String keyword
    ) {
        return pythonAiClient.listIngestBatches(limit, offset, status, parserBackend, keyword);
    }

    @PostMapping("/ingest/batches")
    public Map<String, Object> startIngestBatch(@RequestBody Map<String, Object> body) {
        return pythonAiClient.startIngestBatch(body);
    }

    @PostMapping(value = "/ingest/batches/upload", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public Map<String, Object> uploadIngestBatch(
            @RequestParam("files") List<MultipartFile> files,
            @RequestParam(value = "title", required = false) String title,
            @RequestParam(value = "parser_backend", required = false) String parserBackend,
            @RequestParam(value = "use_parse_cache", required = false) Boolean useParseCache
    ) {
        return pythonAiClient.uploadIngestBatch(files, title, parserBackend, useParseCache);
    }

    @GetMapping("/ingest/jobs/{jobId}")
    public Map<String, Object> getIngestJob(@PathVariable String jobId) {
        return pythonAiClient.getIngestJob(jobId);
    }

    @PostMapping(value = "/ingest", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public Map<String, Object> startPdfIngest(
            @RequestParam(value = "file", required = false) MultipartFile file,
            @RequestParam(value = "doc_id", required = false) String docId,
            @RequestParam(value = "use_parse_cache", required = false) Boolean useParseCache
    ) {
        return pythonAiClient.startPdfIngest(file, docId, useParseCache);
    }

    @GetMapping("/ingest/session-documents")
    public Map<String, Object> listSessionIngestDocuments(
            @RequestParam(defaultValue = "30") int limit,
            @RequestParam(defaultValue = "0") int offset,
            @RequestParam(required = false) String status
    ) {
        return pythonAiClient.listSessionIngestDocuments(limit, offset, status);
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
