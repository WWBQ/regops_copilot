package com.wbq.java_service.controller;

import com.wbq.java_service.client.PythonAiClient;
import com.wbq.java_service.dto.sessions.SessionCreateResponse;
import com.wbq.java_service.dto.sessions.SessionDocumentListResponse;
import com.wbq.java_service.dto.sessions.SessionDocumentResponse;
import com.wbq.java_service.dto.sessions.SessionDocumentUploadResponse;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

@RestController
@RequestMapping("/api/sessions")
public class SessionProxyController {

    private final PythonAiClient pythonAiClient;

    public SessionProxyController(PythonAiClient pythonAiClient) {
        this.pythonAiClient = pythonAiClient;
    }

    @PostMapping
    public SessionCreateResponse createSession() {
        return pythonAiClient.createSession();
    }

    @GetMapping("/{sessionId}/documents")
    public SessionDocumentListResponse listDocuments(@PathVariable String sessionId) {
        return pythonAiClient.listSessionDocuments(sessionId);
    }

    @GetMapping("/{sessionId}/documents/{docId}")
    public SessionDocumentResponse getDocument(
            @PathVariable String sessionId,
            @PathVariable String docId) {
        return pythonAiClient.getSessionDocument(sessionId, docId);
    }

    @PostMapping(value = "/{sessionId}/documents", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public SessionDocumentUploadResponse uploadDocument(
            @PathVariable String sessionId,
            @RequestParam("file") MultipartFile file) {
        return pythonAiClient.uploadSessionDocument(sessionId, file);
    }
}
