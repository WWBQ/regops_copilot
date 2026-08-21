package com.wbq.java_service.client;

import java.util.Map;

import com.wbq.java_service.dto.chat.ChatRequest;
import com.wbq.java_service.dto.chat.ChatResponse;
import com.wbq.java_service.dto.documents.ViewerUrlResponse;
import com.wbq.java_service.dto.sessions.SessionCreateResponse;
import com.wbq.java_service.dto.sessions.SessionDocumentListResponse;
import com.wbq.java_service.dto.sessions.SessionDocumentResponse;
import com.wbq.java_service.dto.sessions.SessionDocumentUploadResponse;
import com.wbq.java_service.exception.PythonAiException;
import com.wbq.java_service.filter.RequestIdFilter;

import org.slf4j.MDC;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.http.MediaType;
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

    private final RestClient restClient;

    public PythonAiClient(RestClient pythonRestClient) {
        this.restClient = pythonRestClient;
    }

    public Map<String, Object> health() {
        return exchange(() -> restClient.get()
                .uri("/health")
                .headers(this::forwardRequestId)
                .retrieve()
                .body(MAP_TYPE));
    }

    public Map<String, Object> models() {
        return exchange(() -> restClient.get()
                .uri("/models")
                .headers(this::forwardRequestId)
                .retrieve()
                .body(MAP_TYPE));
    }

    public ChatResponse chat(ChatRequest request) {
        return exchange(() -> restClient.post()
                .uri("/chat")
                .headers(this::forwardRequestId)
                .contentType(MediaType.APPLICATION_JSON)
                .body(request)
                .retrieve()
                .body(ChatResponse.class));
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
        } catch (Exception ex) {
            throw new PythonAiException(502, "upload failed: " + ex.getMessage());
        }
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

    private void forwardRequestId(org.springframework.http.HttpHeaders headers) {
        String requestId = MDC.get(RequestIdFilter.MDC_KEY);
        if (requestId != null && !requestId.isBlank()) {
            headers.set(RequestIdFilter.HEADER, requestId);
        }
    }

    private <T> T exchange(RestClientSupplier<T> supplier) {
        try {
            T body = supplier.get();
            if (body == null) {
                throw new PythonAiException(502, "python-ai returned empty body");
            }
            return body;
        } catch (RestClientResponseException ex) {
            throw new PythonAiException(ex.getStatusCode().value(), extractDetail(ex));
        } catch (PythonAiException ex) {
            throw ex;
        } catch (Exception ex) {
            throw new PythonAiException(502, "python-ai unavailable: " + ex.getMessage());
        }
    }

    private static String extractDetail(RestClientResponseException ex) {
        String body = ex.getResponseBodyAsString();
        if (body == null || body.isBlank()) {
            return ex.getMessage();
        }
        return body;
    }

    @FunctionalInterface
    private interface RestClientSupplier<T> {
        T get();
    }
}
