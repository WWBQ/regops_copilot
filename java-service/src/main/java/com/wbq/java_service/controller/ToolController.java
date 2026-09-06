package com.wbq.java_service.controller;

import java.util.Map;

import com.wbq.java_service.dto.tools.CompareToolRequest;
import com.wbq.java_service.dto.tools.LookupToolRequest;
import com.wbq.java_service.dto.tools.ReviewDraftRequest;
import com.wbq.java_service.dto.tools.ScopeToolRequest;
import com.wbq.java_service.dto.tools.ToolInvokeHttpRequest;
import com.wbq.java_service.dto.tools.VerifyToolRequest;
import com.wbq.java_service.exception.ToolAccessException;
import com.wbq.java_service.service.FinToolService;
import com.wbq.java_service.tools.FinToolCapabilities;

import jakarta.validation.Valid;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/tools")
public class ToolController {

    private final FinToolService finToolService;

    public ToolController(FinToolService finToolService) {
        this.finToolService = finToolService;
    }

    @GetMapping("/capabilities")
    public Map<String, Object> capabilities() {
        return FinToolCapabilities.body();
    }

    @GetMapping("/schema/{name}")
    public Map<String, Object> schema(@PathVariable String name) {
        Map<String, Object> schema = FinToolCapabilities.schema(name);
        if (schema == null) {
            throw new ToolAccessException(HttpStatus.NOT_FOUND, "unknown_tool", "unknown tool: " + name);
        }
        return schema;
    }

    @PostMapping("/lookup")
    public Map<String, Object> lookup(
            @RequestHeader(value = "X-Regops-Dept", required = false) String dept,
            @Valid @RequestBody LookupToolRequest body
    ) {
        return finToolService.lookup(dept, body);
    }

    @PostMapping("/compare")
    public Map<String, Object> compare(
            @RequestHeader(value = "X-Regops-Dept", required = false) String dept,
            @Valid @RequestBody CompareToolRequest body
    ) {
        return finToolService.compare(dept, body);
    }

    @PostMapping("/scope")
    public Map<String, Object> scope(
            @RequestHeader(value = "X-Regops-Dept", required = false) String dept,
            @Valid @RequestBody(required = false) ScopeToolRequest body
    ) {
        return finToolService.scope(dept, body == null ? new ScopeToolRequest(null, null, null, null) : body);
    }

    @PostMapping("/verify")
    public Map<String, Object> verify(
            @RequestHeader(value = "X-Regops-Dept", required = false) String dept,
            @Valid @RequestBody VerifyToolRequest body
    ) {
        return finToolService.verify(dept, body);
    }

    @PostMapping("/review-draft")
    public Map<String, Object> reviewDraft(
            @RequestHeader(value = "X-Regops-Dept", required = false) String dept,
            @Valid @RequestBody ReviewDraftRequest body
    ) {
        return finToolService.refuseDraft(dept, body);
    }

    @PostMapping("/invoke")
    public Map<String, Object> invoke(
            @RequestHeader(value = "X-Regops-Dept", required = false) String dept,
            @Valid @RequestBody ToolInvokeHttpRequest body
    ) {
        return finToolService.invoke(dept, body);
    }
}
