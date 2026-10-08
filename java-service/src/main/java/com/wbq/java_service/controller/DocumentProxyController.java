package com.wbq.java_service.controller;

import java.util.List;
import java.util.Map;
import java.util.regex.Pattern;

import com.wbq.java_service.auth.AuthSupport;
import com.wbq.java_service.client.PythonAiClient;
import com.wbq.java_service.dto.documents.ViewerUrlResponse;
import com.wbq.java_service.security.DeptAcl;

import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/documents")
public class DocumentProxyController {

    private static final Pattern REPORT_ID = Pattern.compile("^(\\d{6})_\\d{4}(?:_|$)");

    private final PythonAiClient pythonAiClient;

    public DocumentProxyController(PythonAiClient pythonAiClient) {
        this.pythonAiClient = pythonAiClient;
    }

    @GetMapping("/reports")
    public Map<String, Object> annualReports() {
        var user = AuthSupport.requireUser();
        var allowed = DeptAcl.allowlist(user.dept());
        Object rawItems = pythonAiClient.listAnnualReports().get("items");
        if (!(rawItems instanceof List<?> items)) {
            return Map.of("items", List.of());
        }
        var visible = items.stream()
                .filter(item -> item instanceof Map<?, ?>)
                .map(item -> (Map<?, ?>) item)
                .filter(item -> allowed.contains(item.get("company_code")))
                .toList();
        return Map.of("items", visible);
    }

    /**
     * BFF 入口：W7 在此加 JWT / dept_acl 鉴权，再转发 python-ai 签发 viewer URL。
     */
    @GetMapping("/{docId}/viewer-url")
    public ViewerUrlResponse viewerUrl(
            @PathVariable String docId,
            @RequestParam(required = false) Integer page,
            @RequestParam(name = "expires_in", required = false) Integer expiresIn
    ) {
        requireDocumentAccess(docId);
        return pythonAiClient.viewerUrl(docId, page, expiresIn);
    }

    /**
     * 应用内 PDF 预览：inline 流式返回，供前端 iframe 嵌入，不触发下载。
     */
    @GetMapping(value = "/{docId}/content", produces = MediaType.APPLICATION_PDF_VALUE)
    public ResponseEntity<byte[]> documentContent(@PathVariable String docId) {
        requireDocumentAccess(docId);
        byte[] body = pythonAiClient.documentContent(docId);
        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.APPLICATION_PDF);
        headers.set(HttpHeaders.CONTENT_DISPOSITION, "inline; filename=\"" + docId + ".pdf\"");
        headers.setCacheControl("private, max-age=120");
        return new ResponseEntity<>(body, headers, HttpStatus.OK);
    }

    private static void requireDocumentAccess(String docId) {
        var user = AuthSupport.requireUser();
        var matcher = REPORT_ID.matcher(docId);
        if (matcher.find()) {
            DeptAcl.requireCompany(user.dept(), matcher.group(1));
        }
    }
}
