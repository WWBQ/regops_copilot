package com.wbq.java_service.client;

import java.io.InputStream;
import java.io.OutputStream;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.List;
import java.util.Map;

import com.wbq.java_service.config.AppProperties;
import com.wbq.java_service.dto.chat.ChatRequest;
import com.wbq.java_service.dto.chat.ChatResponse;
import com.wbq.java_service.dto.documents.ViewerUrlResponse;
import com.wbq.java_service.dto.sessions.SessionCreateResponse;
import com.wbq.java_service.dto.sessions.SessionDocumentListResponse;
import com.wbq.java_service.dto.sessions.SessionDocumentResponse;
import com.wbq.java_service.dto.sessions.SessionDocumentUploadResponse;
import com.wbq.java_service.exception.PythonAiException;
import com.wbq.java_service.filter.RequestIdFilter;
import com.wbq.java_service.util.ReadRetry;

import tools.jackson.databind.ObjectMapper;

import org.slf4j.MDC;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Component;
import org.springframework.util.LinkedMultiValueMap;
import org.springframework.util.MultiValueMap;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientResponseException;
import org.springframework.web.multipart.MultipartFile;

@Component
public class PythonAiClient {

    private static final ParameterizedTypeReference<Map<String, Object>> MAP_TYPE =
            new ParameterizedTypeReference<>() {
            };

    private static final ParameterizedTypeReference<List<Map<String, Object>>> LIST_MAP_TYPE =
            new ParameterizedTypeReference<>() {
            };

    private final RestClient restClient;
    private final AppProperties properties;
    private final ObjectMapper objectMapper;
    private final HttpClient streamHttpClient;

    public PythonAiClient(RestClient pythonRestClient, AppProperties properties, ObjectMapper objectMapper) {
        this.restClient = pythonRestClient;
        this.properties = properties;
        this.objectMapper = objectMapper;
        this.streamHttpClient = HttpClient.newBuilder()
                .version(HttpClient.Version.HTTP_1_1)
                .connectTimeout(Duration.ofMillis(properties.pythonAi().connectTimeoutMs()))
                .followRedirects(HttpClient.Redirect.NEVER)
                .build();
    }

    public Map<String, Object> health() {
        try {
            String base = properties.pythonAi().baseUrl();
            if (base.endsWith("/")) {
                base = base.substring(0, base.length() - 1);
            }
            HttpRequest.Builder builder = HttpRequest.newBuilder()
                    .uri(URI.create(base + "/health"))
                    .timeout(Duration.ofMillis(properties.pythonAi().resolvedHealthTimeoutMs()))
                    .GET();
            applyCorrelation(builder);
            HttpResponse<String> response = streamHttpClient.send(
                    builder.build(),
                    HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8)
            );
            int status = response.statusCode();
            String body = response.body() == null ? "" : response.body();
            if (status >= 400) {
                throw PythonErrorMapper.fromDownstream(status, body);
            }
            return parseHealthBody(body);
        } catch (PythonAiException ex) {
            throw ex;
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new PythonAiException(502, "python-ai unavailable", "upstream_down");
        } catch (Exception ex) {
            throw PythonErrorMapper.fromTransport(ex);
        }
    }

    public Map<String, Object> models() {
        return exchange(() -> restClient.get()
                .uri("/models")
                .headers(this::forwardRequestId)
                .retrieve()
                .body(MAP_TYPE));
    }

    public ChatResponse chat(ChatRequest request) {
        return chat(request, null);
    }

    public ChatResponse chat(ChatRequest request, String dept) {
        return exchange(() -> restClient.post()
                .uri("/chat")
                .headers(headers -> forwardOutboundHeaders(headers, dept))
                .contentType(MediaType.APPLICATION_JSON)
                .body(request)
                .retrieve()
                .body(ChatResponse.class));
    }

    public void copyChatStream(ChatRequest request, OutputStream output) {
        copyChatStream(request, output, null);
    }

    public void copyChatStream(ChatRequest request, OutputStream output, String dept) {
        try {
            String json = objectMapper.writeValueAsString(request);
            String base = properties.pythonAi().baseUrl();
            if (base.endsWith("/")) {
                base = base.substring(0, base.length() - 1);
            }
            HttpRequest.Builder builder = HttpRequest.newBuilder()
                    .uri(URI.create(base + "/chat/stream"))
                    .timeout(Duration.ofMillis(properties.pythonAi().resolvedStreamTimeoutMs()))
                    .header(HttpHeaders.CONTENT_TYPE, MediaType.APPLICATION_JSON_VALUE)
                    .header(HttpHeaders.ACCEPT, MediaType.TEXT_EVENT_STREAM_VALUE)
                    .POST(HttpRequest.BodyPublishers.ofString(json, StandardCharsets.UTF_8));
            applyCorrelation(builder);
            if (dept != null && !dept.isBlank()) {
                builder.header("X-Regops-Dept", dept);
            }
            var python = properties.pythonAi();
            if (python.serviceName() != null && !python.serviceName().isBlank()) {
                builder.header("X-Regops-Service", python.serviceName());
            }
            if (python.serviceToken() != null && !python.serviceToken().isBlank()) {
                builder.header("X-Regops-Service-Token", python.serviceToken());
            }
            HttpResponse<InputStream> response = streamHttpClient.send(
                    builder.build(),
                    HttpResponse.BodyHandlers.ofInputStream()
            );
            int status = response.statusCode();
            InputStream in = response.body();
            if (status >= 400) {
                byte[] errBytes = in == null ? new byte[0] : in.readAllBytes();
                String err = new String(errBytes, StandardCharsets.UTF_8);
                throw PythonErrorMapper.fromDownstream(status, err);
            }
            if (in == null) {
                throw new PythonAiException(502, "python-ai returned empty stream");
            }
            byte[] buf = new byte[256];
            int n;
            while ((n = in.read(buf)) != -1) {
                output.write(buf, 0, n);
                output.flush();
            }
        } catch (PythonAiException ex) {
            throw ex;
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new PythonAiException(502, "python-ai stream interrupted", "upstream_down");
        } catch (Exception ex) {
            throw PythonErrorMapper.fromTransport(ex);
        }
    }

    public ViewerUrlResponse viewerUrl(String docId, Integer page, Integer expiresIn) {
        Map<String, Object> raw = exchange(() -> restClient.get()
                .uri(uriBuilder -> {
                    var builder = uriBuilder.path("/documents/{docId}/viewer-url");
                    if (page != null) {
                        builder.queryParam("page", page);
                    }
                    if (expiresIn != null) {
                        builder.queryParam("expires_in", expiresIn);
                    }
                    return builder.build(docId);
                })
                .headers(this::forwardRequestId)
                .retrieve()
                .body(MAP_TYPE));
        return new ViewerUrlResponse(
                stringValue(raw.get("doc_id")),
                intValue(raw.get("page")),
                intValue(raw.get("expires_in")),
                stringValue(raw.get("viewer_url"))
        );
    }

    public byte[] documentContent(String docId) {
        byte[] body = exchange(() -> restClient.get()
                .uri("/documents/{docId}/content", docId)
                .headers(this::forwardRequestId)
                .retrieve()
                .body(byte[].class));
        if (body == null) {
            throw new PythonAiException(502, "python-ai returned empty PDF body");
        }
        return body;
    }

    public SessionCreateResponse createSession() {
        return exchange(() -> restClient.post()
                .uri("/sessions")
                .headers(this::forwardRequestId)
                .retrieve()
                .body(SessionCreateResponse.class));
    }

    public SessionDocumentListResponse listSessionDocuments(String sessionId) {
        return exchange(() -> restClient.get()
                .uri("/sessions/{sessionId}/documents", sessionId)
                .headers(this::forwardRequestId)
                .retrieve()
                .body(SessionDocumentListResponse.class));
    }

    public SessionDocumentResponse getSessionDocument(String sessionId, String docId) {
        return exchange(() -> restClient.get()
                .uri("/sessions/{sessionId}/documents/{docId}", sessionId, docId)
                .headers(this::forwardRequestId)
                .retrieve()
                .body(SessionDocumentResponse.class));
    }

    public SessionDocumentUploadResponse uploadSessionDocument(String sessionId, MultipartFile file) {
        try {
            MultiValueMap<String, Object> body = new LinkedMultiValueMap<>();
            String filename = file.getOriginalFilename() != null ? file.getOriginalFilename() : "upload.pdf";
            body.add("file", new ByteArrayResource(file.getBytes()) {
                @Override
                public String getFilename() {
                    return filename;
                }
            });
            return exchange(() -> restClient.post()
                    .uri("/sessions/{sessionId}/documents", sessionId)
                    .headers(this::forwardRequestId)
                    .contentType(MediaType.MULTIPART_FORM_DATA)
                    .body(body)
                    .retrieve()
                    .body(SessionDocumentUploadResponse.class));
        } catch (PythonAiException ex) {
            throw ex;
        } catch (Exception ex) {
            throw PythonErrorMapper.fromTransport(ex);
        }
    }

    public Map<String, Object> getRagOverview() {
        return exchange(() -> restClient.get()
                .uri("/ops/rag/overview")
                .headers(this::forwardRequestId)
                .retrieve()
                .body(MAP_TYPE));
    }

    public Map<String, Object> listRagTraces(int limit, int offset, String outcome) {
        return exchange(() -> restClient.get()
                .uri(uriBuilder -> {
                    var builder = uriBuilder.path("/ops/rag-traces")
                            .queryParam("limit", limit)
                            .queryParam("offset", offset);
                    if (outcome != null && !outcome.isBlank()) {
                        builder.queryParam("outcome", outcome);
                    }
                    return builder.build();
                })
                .headers(this::forwardRequestId)
                .retrieve()
                .body(MAP_TYPE));
    }

    public Map<String, Object> getRagTrace(int traceId) {
        return exchange(() -> restClient.get()
                .uri("/ops/rag-traces/{traceId}", traceId)
                .headers(this::forwardRequestId)
                .retrieve()
                .body(MAP_TYPE));
    }

    public Map<String, Object> listAsknumTraces(int limit, int offset, String route) {
        return exchange(() -> restClient.get()
                .uri(uriBuilder -> {
                    var builder = uriBuilder.path("/ops/asknum-traces")
                            .queryParam("limit", limit)
                            .queryParam("offset", offset);
                    if (route != null && !route.isBlank()) {
                        builder.queryParam("route", route);
                    }
                    return builder.build();
                })
                .headers(this::forwardRequestId)
                .retrieve()
                .body(MAP_TYPE));
    }

    public Map<String, Object> getAsknumTrace(int traceId) {
        return exchange(() -> restClient.get()
                .uri("/ops/asknum-traces/{traceId}", traceId)
                .headers(this::forwardRequestId)
                .retrieve()
                .body(MAP_TYPE));
    }

    public Map<String, Object> listEvalTasks() {
        return exchange(() -> restClient.get()
                .uri("/ops/eval/tasks")
                .headers(this::forwardRequestId)
                .retrieve()
                .body(MAP_TYPE));
    }

    public Map<String, Object> listEvalRuns(String taskId, int limit) {
        return exchange(() -> restClient.get()
                .uri(uriBuilder -> {
                    var builder = uriBuilder.path("/ops/eval/runs")
                            .queryParam("limit", limit);
                    if (taskId != null && !taskId.isBlank()) {
                        builder.queryParam("task_id", taskId);
                    }
                    return builder.build();
                })
                .headers(this::forwardRequestId)
                .retrieve()
                .body(MAP_TYPE));
    }

    public Map<String, Object> getEvalRun(String runId, boolean includeReport) {
        return exchange(() -> restClient.get()
                .uri(uriBuilder -> uriBuilder.path("/ops/eval/runs/{runId}")
                        .queryParam("include_report", includeReport)
                        .build(runId))
                .headers(this::forwardRequestId)
                .retrieve()
                .body(MAP_TYPE));
    }

    public Map<String, Object> startEvalRun(Map<String, Object> body) {
        return exchange(() -> restClient.post()
                .uri("/ops/eval/runs")
                .headers(this::forwardRequestId)
                .contentType(org.springframework.http.MediaType.APPLICATION_JSON)
                .body(body)
                .retrieve()
                .body(MAP_TYPE));
    }

    public Map<String, Object> listEvalGoldenSets() {
        return exchange(() -> restClient.get()
                .uri("/ops/eval/golden-sets")
                .headers(this::forwardRequestId)
                .retrieve()
                .body(MAP_TYPE));
    }

    public Map<String, Object> getEvalGoldenSet(String filename) {
        return exchange(() -> restClient.get()
                .uri("/ops/eval/golden-sets/{filename}", filename)
                .headers(this::forwardRequestId)
                .retrieve()
                .body(MAP_TYPE));
    }

    public Map<String, Object> uploadEvalGoldenSet(Map<String, Object> body) {
        return exchange(() -> restClient.post()
                .uri("/ops/eval/golden-sets/upload")
                .headers(this::forwardRequestId)
                .contentType(org.springframework.http.MediaType.APPLICATION_JSON)
                .body(body)
                .retrieve()
                .body(MAP_TYPE));
    }

    public Map<String, Object> createEvalTask(Map<String, Object> body) {
        return exchange(() -> restClient.post()
                .uri("/ops/eval/tasks")
                .headers(this::forwardRequestId)
                .contentType(org.springframework.http.MediaType.APPLICATION_JSON)
                .body(body)
                .retrieve()
                .body(MAP_TYPE));
    }

    public Map<String, Object> deleteEvalTask(String taskId) {
        return exchange(() -> restClient.delete()
                .uri("/ops/eval/tasks/{taskId}", taskId)
                .headers(this::forwardRequestId)
                .retrieve()
                .body(MAP_TYPE));
    }

    public Map<String, Object> deleteEvalRun(String runId) {
        return exchange(() -> restClient.delete()
                .uri("/ops/eval/runs/{runId}", runId)
                .headers(this::forwardRequestId)
                .retrieve()
                .body(MAP_TYPE));
    }

    public Map<String, Object> getSystemOverview() {
        return exchange(() -> restClient.get()
                .uri("/ops/system/overview")
                .headers(this::forwardRequestId)
                .retrieve()
                .body(MAP_TYPE));
    }

    public Map<String, Object> getObsOverview() {
        return exchange(() -> restClient.get()
                .uri("/ops/obs/overview")
                .headers(this::forwardRequestId)
                .retrieve()
                .body(MAP_TYPE));
    }

    public Map<String, Object> listObsTraces(int limit, int offset) {
        return exchange(() -> restClient.get()
                .uri(uriBuilder -> uriBuilder.path("/ops/obs/traces")
                        .queryParam("limit", limit)
                        .queryParam("offset", offset)
                        .build())
                .headers(this::forwardRequestId)
                .retrieve()
                .body(MAP_TYPE));
    }

    public Map<String, Object> getIngestOverview() {
        return exchange(() -> restClient.get()
                .uri("/ops/ingest/overview")
                .headers(this::forwardRequestId)
                .retrieve()
                .body(MAP_TYPE));
    }

    public Map<String, Object> listIngestJobs(Integer limit, Integer offset, String status, String targetType) {
        return exchange(() -> restClient.get()
                .uri(uriBuilder -> {
                    var builder = uriBuilder.path("/ops/ingest/jobs");
                    if (limit != null) {
                        builder.queryParam("limit", limit);
                    }
                    if (offset != null) {
                        builder.queryParam("offset", offset);
                    }
                    if (status != null && !status.isBlank()) {
                        builder.queryParam("status", status);
                    }
                    if (targetType != null && !targetType.isBlank()) {
                        builder.queryParam("target_type", targetType);
                    }
                    return builder.build();
                })
                .headers(this::forwardRequestId)
                .retrieve()
                .body(MAP_TYPE));
    }

    public Map<String, Object> getIngestJob(String jobId) {
        return exchange(() -> restClient.get()
                .uri("/ops/ingest/jobs/{jobId}", jobId)
                .headers(this::forwardRequestId)
                .retrieve()
                .body(MAP_TYPE));
    }

    public Map<String, Object> startPdfIngest(MultipartFile file, String docId, Boolean useParseCache) {
        try {
            MultiValueMap<String, Object> body = new LinkedMultiValueMap<>();
            if (file != null && !file.isEmpty()) {
                String filename = file.getOriginalFilename() != null ? file.getOriginalFilename() : "upload.pdf";
                body.add("file", new ByteArrayResource(file.getBytes()) {
                    @Override
                    public String getFilename() {
                        return filename;
                    }
                });
            }
            if (docId != null && !docId.isBlank()) {
                body.add("doc_id", docId);
            }
            if (useParseCache != null) {
                body.add("use_parse_cache", String.valueOf(useParseCache));
            }
            return exchange(() -> restClient.post()
                    .uri("/ingest")
                    .headers(this::forwardRequestId)
                    .contentType(MediaType.MULTIPART_FORM_DATA)
                    .body(body)
                    .retrieve()
                    .body(MAP_TYPE));
        } catch (PythonAiException ex) {
            throw ex;
        } catch (Exception ex) {
            throw PythonErrorMapper.fromTransport(ex);
        }
    }

    public Map<String, Object> listSessionIngestDocuments(Integer limit, Integer offset, String status) {
        return exchange(() -> restClient.get()
                .uri(uriBuilder -> {
                    var builder = uriBuilder.path("/ops/ingest/session-documents");
                    if (limit != null) {
                        builder.queryParam("limit", limit);
                    }
                    if (offset != null) {
                        builder.queryParam("offset", offset);
                    }
                    if (status != null && !status.isBlank()) {
                        builder.queryParam("status", status);
                    }
                    return builder.build();
                })
                .headers(this::forwardRequestId)
                .retrieve()
                .body(MAP_TYPE));
    }

    public Map<String, Object> getQualityGates() {
        return exchange(() -> restClient.get()
                .uri("/ops/quality/gates")
                .headers(this::forwardRequestId)
                .retrieve()
                .body(MAP_TYPE));
    }

    public Map<String, Object> listQualityFacts(
            Integer limit,
            Integer offset,
            String companyCode,
            String status,
            String statement,
            String concept,
            String docId
    ) {
        return exchange(() -> restClient.get()
                .uri(uriBuilder -> {
                    var builder = uriBuilder.path("/ops/quality/facts");
                    if (limit != null) {
                        builder.queryParam("limit", limit);
                    }
                    if (offset != null) {
                        builder.queryParam("offset", offset);
                    }
                    if (companyCode != null && !companyCode.isBlank()) {
                        builder.queryParam("company_code", companyCode);
                    }
                    if (status != null && !status.isBlank()) {
                        builder.queryParam("status", status);
                    }
                    if (statement != null && !statement.isBlank()) {
                        builder.queryParam("statement", statement);
                    }
                    if (concept != null && !concept.isBlank()) {
                        builder.queryParam("concept", concept);
                    }
                    if (docId != null && !docId.isBlank()) {
                        builder.queryParam("doc_id", docId);
                    }
                    return builder.build();
                })
                .headers(this::forwardRequestId)
                .retrieve()
                .body(MAP_TYPE));
    }

    public Map<String, Object> ingestQualityFacts(Map<String, Object> body) {
        return exchange(() -> restClient.post()
                .uri("/ops/quality/ingest")
                .headers(this::forwardRequestId)
                .contentType(org.springframework.http.MediaType.APPLICATION_JSON)
                .body(body)
                .retrieve()
                .body(MAP_TYPE));
    }

    public List<Map<String, Object>> listLabelTasks() {
        return exchange(() -> restClient.get()
                .uri("/labeling/tasks")
                .headers(this::forwardRequestId)
                .retrieve()
                .body(LIST_MAP_TYPE));
    }

    public Map<String, Object> createLabelTask(
            String name,
            String desc,
            String urlType,
            String labelOptions,
            MultipartFile file
    ) {
        try {
            MultiValueMap<String, Object> body = new LinkedMultiValueMap<>();
            body.add("name", name);
            body.add("desc", desc != null ? desc : "");
            body.add("url_type", urlType != null ? urlType : "pdf");
            body.add("label_options", labelOptions != null ? labelOptions : "");
            String filename = file.getOriginalFilename() != null ? file.getOriginalFilename() : "data.xlsx";
            body.add("file", new ByteArrayResource(file.getBytes()) {
                @Override
                public String getFilename() {
                    return filename;
                }
            });
            return exchange(() -> restClient.post()
                    .uri("/labeling/tasks")
                    .headers(this::forwardRequestId)
                    .contentType(MediaType.MULTIPART_FORM_DATA)
                    .body(body)
                    .retrieve()
                    .body(MAP_TYPE));
        } catch (PythonAiException ex) {
            throw ex;
        } catch (Exception ex) {
            throw PythonErrorMapper.fromTransport(ex);
        }
    }

    public Map<String, Object> getLabelTask(String taskId) {
        return exchange(() -> restClient.get()
                .uri("/labeling/tasks/{taskId}", taskId)
                .headers(this::forwardRequestId)
                .retrieve()
                .body(MAP_TYPE));
    }

    public Map<String, Object> getLabelItem(String taskId, int idx) {
        return exchange(() -> restClient.get()
                .uri("/labeling/tasks/{taskId}/items/{idx}", taskId, idx)
                .headers(this::forwardRequestId)
                .retrieve()
                .body(MAP_TYPE));
    }

    public Map<String, Object> saveLabelItem(String taskId, int idx, Map<String, Object> body) {
        return exchange(() -> restClient.post()
                .uri("/labeling/tasks/{taskId}/items/{idx}", taskId, idx)
                .headers(this::forwardRequestId)
                .contentType(MediaType.APPLICATION_JSON)
                .body(body)
                .retrieve()
                .body(MAP_TYPE));
    }

    public ResponseEntity<byte[]> labelingTemplate() {
        return proxyGetBytes("/labeling/template");
    }

    public ResponseEntity<byte[]> exportLabelTask(String taskId) {
        return proxyGetBytes("/labeling/tasks/{taskId}/export", taskId);
    }

    public ResponseEntity<byte[]> labelingPdf(String taskId, String filename) {
        return proxyGetBytes("/labeling/tasks/{taskId}/pdf/{filename}", taskId, filename);
    }

    public ResponseEntity<byte[]> labelingHtml(String taskId, int idx) {
        return proxyGetBytes("/labeling/tasks/{taskId}/html/{idx}", taskId, idx);
    }

    public Map<String, Object> listLogEvents(Integer limit, Integer offset, String source, String level) {
        return exchange(() -> restClient.get()
                .uri(uriBuilder -> {
                    var builder = uriBuilder.path("/ops/logs/events");
                    if (limit != null) {
                        builder.queryParam("limit", limit);
                    }
                    if (offset != null) {
                        builder.queryParam("offset", offset);
                    }
                    if (source != null && !source.isBlank()) {
                        builder.queryParam("source", source);
                    }
                    if (level != null && !level.isBlank()) {
                        builder.queryParam("level", level);
                    }
                    return builder.build();
                })
                .headers(this::forwardRequestId)
                .retrieve()
                .body(MAP_TYPE));
    }

    private ResponseEntity<byte[]> proxyGetBytes(String path, Object... uriVars) {
        ResponseEntity<byte[]> downstream = exchange(() -> restClient.get()
                .uri(path, uriVars)
                .headers(this::forwardRequestId)
                .retrieve()
                .toEntity(byte[].class));
        byte[] body = downstream.getBody();
        if (body == null) {
            throw new PythonAiException(502, "python-ai returned empty body");
        }
        HttpHeaders headers = new HttpHeaders();
        MediaType contentType = downstream.getHeaders().getContentType();
        headers.setContentType(contentType != null ? contentType : MediaType.APPLICATION_OCTET_STREAM);
        String disposition = downstream.getHeaders().getFirst(HttpHeaders.CONTENT_DISPOSITION);
        if (disposition != null && !disposition.isBlank()) {
            headers.set(HttpHeaders.CONTENT_DISPOSITION, disposition);
        }
        return new ResponseEntity<>(body, headers, HttpStatus.OK);
    }

    private static String stringValue(Object value) {
        return value == null ? null : String.valueOf(value);
    }

    private static Integer intValue(Object value) {
        if (value == null) {
            return null;
        }
        if (value instanceof Number number) {
            return number.intValue();
        }
        return Integer.parseInt(String.valueOf(value));
    }

    private void applyCorrelation(HttpRequest.Builder builder) {
        String requestId = MDC.get(RequestIdFilter.MDC_KEY);
        if (requestId != null && !requestId.isBlank()) {
            builder.header(RequestIdFilter.HEADER, requestId);
        }
        String traceparent = MDC.get(RequestIdFilter.TRACEPARENT_MDC_KEY);
        if (traceparent != null && !traceparent.isBlank()) {
            builder.header(RequestIdFilter.TRACEPARENT_HEADER, traceparent);
        }
    }

    private void forwardRequestId(org.springframework.http.HttpHeaders headers) {
        forwardOutboundHeaders(headers, null);
    }

    private void forwardOutboundHeaders(org.springframework.http.HttpHeaders headers, String dept) {
        String requestId = MDC.get(RequestIdFilter.MDC_KEY);
        if (requestId != null && !requestId.isBlank()) {
            headers.set(RequestIdFilter.HEADER, requestId);
        }
        String traceparent = MDC.get(RequestIdFilter.TRACEPARENT_MDC_KEY);
        if (traceparent != null && !traceparent.isBlank()) {
            headers.set(RequestIdFilter.TRACEPARENT_HEADER, traceparent);
        }
        var python = properties.pythonAi();
        if (python.serviceName() != null && !python.serviceName().isBlank()) {
            headers.set("X-Regops-Service", python.serviceName());
        }
        if (python.serviceToken() != null && !python.serviceToken().isBlank()) {
            headers.set("X-Regops-Service-Token", python.serviceToken());
        }
        if (dept != null && !dept.isBlank()) {
            headers.set("X-Regops-Dept", dept);
        }
        headers.remove(HttpHeaders.AUTHORIZATION);
    }

    private <T> T exchangeRead(RestClientSupplier<T> supplier) {
        return ReadRetry.call(properties.pythonAi().resolvedReadRetryCount(), () -> exchange(supplier));
    }

    private <T> T exchange(RestClientSupplier<T> supplier) {
        try {
            T body = supplier.get();
            if (body == null) {
                throw new PythonAiException(502, "python-ai returned empty body");
            }
            return body;
        } catch (RestClientResponseException ex) {
            throw PythonErrorMapper.fromDownstream(ex.getStatusCode().value(), ex.getResponseBodyAsString());
        } catch (PythonAiException ex) {
            throw ex;
        } catch (Exception ex) {
            throw PythonErrorMapper.fromTransport(ex);
        }
    }

    private Map<String, Object> parseHealthBody(String body) {
        if (body == null || body.isBlank()) {
            throw new PythonAiException(502, "python-ai returned empty body", "upstream_down");
        }
        try {
            var node = objectMapper.readTree(body);
            Map<String, Object> out = new java.util.LinkedHashMap<>();
            var status = node.get("status");
            out.put("status", status == null || status.isNull() || !status.isString() || status.asString().isBlank()
                    ? "ok"
                    : status.asString());
            var service = node.get("service");
            if (service != null && service.isString() && !service.asString().isBlank()) {
                out.put("service", service.asString());
            }
            return out;
        } catch (PythonAiException ex) {
            throw ex;
        } catch (Exception ex) {
            return Map.of("status", "ok");
        }
    }

    @FunctionalInterface
    private interface RestClientSupplier<T> {
        T get();
    }
}
