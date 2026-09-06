package com.wbq.java_service.controller;

import java.util.List;
import java.util.Map;

import com.wbq.java_service.client.PythonAiClient;

import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

@RestController
@RequestMapping("/api/labeling")
public class LabelingProxyController {

    private final PythonAiClient pythonAiClient;

    public LabelingProxyController(PythonAiClient pythonAiClient) {
        this.pythonAiClient = pythonAiClient;
    }

    @GetMapping("/tasks")
    public List<Map<String, Object>> listTasks() {
        return pythonAiClient.listLabelTasks();
    }

    @GetMapping("/template")
    public ResponseEntity<byte[]> downloadTemplate() {
        return pythonAiClient.labelingTemplate();
    }

    @PostMapping(value = "/tasks", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public Map<String, Object> createTask(
            @RequestParam("name") String name,
            @RequestParam(value = "desc", defaultValue = "") String desc,
            @RequestParam(value = "url_type", defaultValue = "pdf") String urlType,
            @RequestParam(value = "label_options", defaultValue = "") String labelOptions,
            @RequestParam("file") MultipartFile file
    ) {
        return pythonAiClient.createLabelTask(name, desc, urlType, labelOptions, file);
    }

    @GetMapping("/tasks/{taskId}")
    public Map<String, Object> getTask(@PathVariable String taskId) {
        return pythonAiClient.getLabelTask(taskId);
    }

    @GetMapping("/tasks/{taskId}/items/{idx}")
    public Map<String, Object> getItem(@PathVariable String taskId, @PathVariable int idx) {
        return pythonAiClient.getLabelItem(taskId, idx);
    }

    @PostMapping("/tasks/{taskId}/items/{idx}")
    public Map<String, Object> saveItem(
            @PathVariable String taskId,
            @PathVariable int idx,
            @RequestBody Map<String, Object> body
    ) {
        return pythonAiClient.saveLabelItem(taskId, idx, body);
    }

    @GetMapping("/tasks/{taskId}/export")
    public ResponseEntity<byte[]> exportTask(@PathVariable String taskId) {
        return pythonAiClient.exportLabelTask(taskId);
    }

    @GetMapping("/tasks/{taskId}/pdf/{filename}")
    public ResponseEntity<byte[]> servePdf(
            @PathVariable String taskId,
            @PathVariable String filename
    ) {
        return pythonAiClient.labelingPdf(taskId, filename);
    }

    @GetMapping("/tasks/{taskId}/html/{idx}")
    public ResponseEntity<byte[]> proxyHtml(@PathVariable String taskId, @PathVariable int idx) {
        return pythonAiClient.labelingHtml(taskId, idx);
    }
}
