package com.wbq.java_service.client;

import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.URI;
import java.net.URLEncoder;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.UUID;
import java.util.HashMap;
import java.util.Map;

import com.wbq.java_service.config.AppProperties;
import com.wbq.java_service.exception.PythonAiException;

import org.springframework.stereotype.Component;

import tools.jackson.databind.ObjectMapper;

/** Same-origin BFF bridge to the read-only financial risk Agent's conversation API. */
@Component
public class RiskAgentClient {

    private final HttpClient client = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(5))
            .followRedirects(HttpClient.Redirect.NEVER)
            .build();
    private final AppProperties.RiskAgentProperties settings;
    private final ObjectMapper mapper;

    public RiskAgentClient(AppProperties properties, ObjectMapper mapper) {
        this.settings = properties.riskAgent();
        this.mapper = mapper;
    }

    public Object get(String path, UUID userId) {
        try {
            HttpRequest request = request(path, userId)
                    .timeout(Duration.ofSeconds(30))
                    .GET()
                    .build();
            HttpResponse<String> response = client.send(request, HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
            checkResponse(response.statusCode(), response.body());
            return mapper.readValue(response.body(), Object.class);
        } catch (PythonAiException ex) {
            throw ex;
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw unavailable();
        } catch (Exception ex) {
            throw unavailable();
        }
    }

    public Object post(String path, UUID userId) {
        return postBytes(path, new byte[0], "application/json", userId);
    }

    public Object uploadCodeFile(String path, String filename, byte[] content, UUID userId) {
        if (content == null || content.length == 0 || content.length > 20 * 1024 * 1024) {
            throw new PythonAiException(413, "上传文件必须在 1 字节至 20 MiB 之间", "upload_too_large");
        }
        String encoded = URLEncoder.encode(filename, StandardCharsets.UTF_8);
        return postBytes(path + "?filename=" + encoded, content, "application/octet-stream", userId);
    }

    private Object postBytes(String path, byte[] content, String contentType, UUID userId) {
        try {
            HttpRequest request = request(path, userId)
                    .timeout(Duration.ofMinutes(4))
                    .header("Content-Type", contentType)
                    .POST(HttpRequest.BodyPublishers.ofByteArray(content))
                    .build();
            HttpResponse<String> response = client.send(request, HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
            checkResponse(response.statusCode(), response.body());
            return mapper.readValue(response.body(), Object.class);
        } catch (PythonAiException ex) {
            throw ex;
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw unavailable();
        } catch (Exception ex) {
            throw unavailable();
        }
    }

    public byte[] downloadArchive(String path, UUID userId) {
        try {
            HttpRequest request = request(path, userId)
                    .timeout(Duration.ofMinutes(2))
                    .GET()
                    .build();
            HttpResponse<InputStream> response = client.send(request, HttpResponse.BodyHandlers.ofInputStream());
            try (InputStream body = response.body()) {
                if (response.statusCode() >= 400) {
                    checkResponse(response.statusCode(), new String(body.readNBytes(8192), StandardCharsets.UTF_8));
                }
                checkResponse(response.statusCode(), "");
                byte[] archive = body.readNBytes(20 * 1024 * 1024 + 1);
                if (archive.length > 20 * 1024 * 1024) {
                    throw new PythonAiException(413, "沙箱导出超过 20 MiB", "archive_too_large");
                }
                return archive;
            }
        } catch (PythonAiException ex) {
            throw ex;
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw unavailable();
        } catch (Exception ex) {
            throw unavailable();
        }
    }

    public void deleteThread(String threadId, UUID userId) {
        deleteThread("/regops/agent", threadId, userId);
    }

    public void deleteThread(String apiPrefix, String threadId, UUID userId) {
        try {
            HttpRequest request = request(apiPrefix + "/threads/" + checkedThreadId(threadId), userId)
                    .timeout(Duration.ofSeconds(30))
                    .DELETE()
                    .build();
            HttpResponse<String> response = client.send(request, HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
            checkResponse(response.statusCode(), response.body());
        } catch (PythonAiException ex) {
            throw ex;
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw unavailable();
        } catch (Exception ex) {
            throw unavailable();
        }
    }

    /** Opens the upstream before sending HTTP 200 to the browser, preserving early 4xx/5xx errors. */
    public InputStream openStream(String threadId, String content, String modelId, UUID userId) {
        return openStream("/regops/agent", threadId, content, modelId, userId);
    }

    public InputStream openStream(String apiPrefix, String threadId, String content, String modelId, UUID userId) {
        try {
            String path = threadId == null
                    ? apiPrefix + "/threads/stream-message"
                    : apiPrefix + "/threads/" + checkedThreadId(threadId) + "/stream-message";
            Map<String, String> payload = new HashMap<>();
            payload.put("content", content);
            if (modelId != null) {
                payload.put("model_id", modelId);
            }
            String body = mapper.writeValueAsString(payload);
            HttpRequest request = request(path, userId)
                    .timeout(Duration.ofMinutes(10))
                    .header("Content-Type", "application/json")
                    .header("Accept", "text/event-stream")
                    .POST(HttpRequest.BodyPublishers.ofString(body, StandardCharsets.UTF_8))
                    .build();
            HttpResponse<InputStream> response = client.send(request, HttpResponse.BodyHandlers.ofInputStream());
            if (response.statusCode() >= 400) {
                try (InputStream errorBody = response.body()) {
                    checkResponse(response.statusCode(), new String(errorBody.readAllBytes(), StandardCharsets.UTF_8));
                }
            }
            if (response.body() == null) {
                throw unavailable();
            }
            return response.body();
        } catch (PythonAiException ex) {
            throw ex;
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw unavailable();
        } catch (Exception ex) {
            throw unavailable();
        }
    }

    public void copyStream(InputStream upstream, OutputStream downstream) throws IOException {
        try (upstream) {
            byte[] buffer = new byte[256];
            int count;
            while ((count = upstream.read(buffer)) != -1) {
                downstream.write(buffer, 0, count);
                downstream.flush();
            }
        }
    }

    private HttpRequest.Builder request(String path, UUID userId) {
        if (settings == null || settings.serviceToken().isBlank()) {
            throw unavailable();
        }
        String base = settings.baseUrl().replaceAll("/+$", "");
        return HttpRequest.newBuilder(URI.create(base + path))
                .header("X-Regops-Service-Token", settings.serviceToken())
                .header("X-Regops-User", userId.toString());
    }

    private String checkedThreadId(String threadId) {
        if (!threadId.matches("[0-9a-fA-F-]{36}_(coding_)?[0-9a-fA-F-]{36}")) {
            throw new PythonAiException(404, "thread not found", "not_found");
        }
        return threadId;
    }

    private void checkResponse(int status, String body) {
        if (status == 401 || status == 403) {
            throw new PythonAiException(502, "Agent 服务认证配置不一致", "upstream_down");
        }
        if (status >= 400) {
            throw PythonErrorMapper.fromDownstream(status, body);
        }
        if (status < 200 || status >= 300) {
            throw unavailable();
        }
    }

    private PythonAiException unavailable() {
        return new PythonAiException(502, "Agent 服务暂不可用", "upstream_down");
    }
}
