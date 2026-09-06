package com.wbq.java_service.controller;

import java.util.Map;

import com.wbq.java_service.client.PythonAiClient;

import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/ops/eval")
public class EvalProxyController {

    private final PythonAiClient pythonAiClient;

    public EvalProxyController(PythonAiClient pythonAiClient) {
        this.pythonAiClient = pythonAiClient;
    }

    @GetMapping("/tasks")
    public Map<String, Object> listTasks() {
        return pythonAiClient.listEvalTasks();
    }

    @GetMapping("/golden-sets")
    public Map<String, Object> listGoldenSets() {
        return pythonAiClient.listEvalGoldenSets();
    }

    @GetMapping("/golden-sets/{filename:.+}")
    public Map<String, Object> getGoldenSet(@PathVariable String filename) {
        return pythonAiClient.getEvalGoldenSet(filename);
    }

    @PostMapping("/golden-sets/upload")
    public Map<String, Object> uploadGoldenSet(@RequestBody Map<String, Object> body) {
        return pythonAiClient.uploadEvalGoldenSet(body);
    }

    @PostMapping("/tasks")
    public Map<String, Object> createTask(@RequestBody Map<String, Object> body) {
        return pythonAiClient.createEvalTask(body);
    }

    @DeleteMapping("/tasks/{taskId}")
    public Map<String, Object> deleteTask(@PathVariable String taskId) {
        return pythonAiClient.deleteEvalTask(taskId);
    }

    @GetMapping("/runs")
    public Map<String, Object> listRuns(
            @RequestParam(value = "task_id", required = false) String taskId,
            @RequestParam(defaultValue = "30") int limit
    ) {
        return pythonAiClient.listEvalRuns(taskId, limit);
    }

    @GetMapping("/runs/{runId}")
    public Map<String, Object> getRun(
            @PathVariable String runId,
            @RequestParam(defaultValue = "true") boolean includeReport
    ) {
        return pythonAiClient.getEvalRun(runId, includeReport);
    }

    @DeleteMapping("/runs/{runId}")
    public Map<String, Object> deleteRun(@PathVariable String runId) {
        return pythonAiClient.deleteEvalRun(runId);
    }

    @PostMapping("/runs")
    public Map<String, Object> startRun(@RequestBody Map<String, Object> body) {
        return pythonAiClient.startEvalRun(body);
    }
}
