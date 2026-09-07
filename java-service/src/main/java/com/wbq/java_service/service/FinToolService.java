package com.wbq.java_service.service;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

import com.wbq.java_service.auth.AuthSupport;
import com.wbq.java_service.client.PythonAiClient;
import com.wbq.java_service.dto.tools.CompareToolRequest;
import com.wbq.java_service.dto.tools.LookupToolRequest;
import com.wbq.java_service.dto.tools.ReviewDraftRequest;
import com.wbq.java_service.dto.tools.ScopeToolRequest;
import com.wbq.java_service.dto.tools.ToolInvokeHttpRequest;
import com.wbq.java_service.dto.tools.VerifyToolRequest;
import com.wbq.java_service.exception.ToolAccessException;
import com.wbq.java_service.tools.DeptAcl;
import com.wbq.java_service.util.PiiMask;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;

@Service
public class FinToolService {

    private static final Logger log = LoggerFactory.getLogger(FinToolService.class);
    private static final Set<String> JAVA_FORBIDDEN = Set.of("rag_search", "emit_conclusion", "execute_sql");

    private final PythonAiClient pythonAiClient;

    public FinToolService(PythonAiClient pythonAiClient) {
        this.pythonAiClient = pythonAiClient;
    }

    public Map<String, Object> lookup(String dept, LookupToolRequest request) {
        dept = AuthSupport.resolveDept(dept);
        DeptAcl.requireCompany(dept, request.companyCode());
        Map<String, Object> args = metricArgs(request.companyCode(), request.concept(), request.year(), request.scopeOrDefault());
        return invokeRead("lookup_metric", args, dept, request.backend());
    }

    public Map<String, Object> compare(String dept, CompareToolRequest request) {
        dept = AuthSupport.resolveDept(dept);
        DeptAcl.requireCompanies(dept, request.companyCodes());
        Map<String, Object> args = new LinkedHashMap<>();
        args.put("company_codes", request.companyCodes());
        args.put("concept", request.concept());
        args.put("year", request.year());
        args.put("scope", request.scopeOrDefault());
        return invokeRead("compare_peers", args, dept, request.backend());
    }

    public Map<String, Object> scope(String dept, ScopeToolRequest request) {
        dept = AuthSupport.resolveDept(dept);
        DeptAcl.requireDept(dept);
        if (request.companyCode() != null && !request.companyCode().isBlank()) {
            DeptAcl.requireCompany(dept, request.companyCode());
        }
        Map<String, Object> args = new LinkedHashMap<>();
        if (request.companyCode() != null && !request.companyCode().isBlank()) {
            args.put("company_code", request.companyCode());
        }
        if (request.year() != null) {
            args.put("year", request.year());
        }
        if (request.scope() != null && !request.scope().isBlank()) {
            args.put("scope", request.scope());
        }
        args.put("accepted_only", true);
        return invokeRead("list_scope", args, dept, request.backend());
    }

    public Map<String, Object> verify(String dept, VerifyToolRequest request) {
        dept = AuthSupport.resolveDept(dept);
        DeptAcl.requireCompany(dept, request.companyCode());
        Map<String, Object> args = metricArgs(request.companyCode(), request.concept(), request.year(), request.scopeOrDefault());
        args.put("claimed", request.claimed());
        return invokeRead("verify_number", args, dept, request.backend());
    }

    public Map<String, Object> createDraft(String dept, ReviewDraftRequest request) {
        dept = AuthSupport.resolveDept(dept);
        if (AuthSupport.isRm()) {
            throw new ToolAccessException("unauthorized", "客户经理不能创建审查工单");
        }
        DeptAcl.requireCompany(dept, request.companyCode());
        if (request.companyCodes() != null && !request.companyCodes().isEmpty()) {
            DeptAcl.requireCompanies(dept, request.companyCodes());
        }
        log.info("write draft dept={} company={}", dept, request.companyCode());
        Map<String, Object> args = new LinkedHashMap<>();
        args.put("company_code", request.companyCode());
        args.put("title", request.title());
        args.put("reason", request.reason());
        args.put("dept", dept);
        putIfPresent(args, "company_codes", request.companyCodes());
        putIfPresent(args, "conclusion", request.conclusion());
        putIfPresent(args, "risk_level", request.riskLevel());
        putIfPresent(args, "clause_refs", request.clauseRefs());
        putIfPresent(args, "evidence_quotes", request.evidenceQuotes());
        putIfPresent(args, "impact_scope", request.impactScope());
        putIfPresent(args, "thread_id", request.threadId());
        return pythonAiClient.invokeToolWrite(
                "create_review_draft",
                args,
                dept,
                request.backend(),
                request.threadId()
        );
    }

    public Map<String, Object> listDrafts(String dept, int limit, int offset) {
        dept = AuthSupport.resolveDept(dept);
        if (AuthSupport.isRm()) {
            throw new ToolAccessException("unauthorized", "客户经理不能查看审查工单");
        }
        DeptAcl.requireDept(dept);
        return pythonAiClient.listReviewDrafts(dept, limit, offset);
    }

    public Map<String, Object> getDraft(String dept, String draftId) {
        dept = AuthSupport.resolveDept(dept);
        if (AuthSupport.isRm()) {
            throw new ToolAccessException("unauthorized", "客户经理不能查看审查工单");
        }
        DeptAcl.requireDept(dept);
        return pythonAiClient.getReviewDraft(dept, draftId);
    }

    public Map<String, Object> invoke(String dept, ToolInvokeHttpRequest request) {
        dept = AuthSupport.resolveDept(dept);
        String name = request.name();
        if (JAVA_FORBIDDEN.contains(name)) {
            throw new ToolAccessException(HttpStatus.BAD_REQUEST, "invalid_params", "Java 不代理 " + name + "，走 Python /tools");
        }
        DeptAcl.requireDept(dept);
        Map<String, Object> arguments = request.arguments() == null ? Map.of() : request.arguments();
        Object codes = arguments.get("company_codes");
        Object code = arguments.get("company_code");
        if (codes instanceof List<?> list) {
            DeptAcl.requireCompanies(dept, list.stream().map(String::valueOf).toList());
        } else if (code != null) {
            DeptAcl.requireCompany(dept, String.valueOf(code));
        }
        if ("create_review_draft".equals(name)) {
            if (AuthSupport.isRm()) {
                throw new ToolAccessException("unauthorized", "客户经理不能创建审查工单");
            }
            Object threadId = arguments.get("thread_id");
            String key = threadId == null ? null : String.valueOf(threadId);
            return pythonAiClient.invokeToolWrite(name, arguments, dept, request.backend(), key);
        }
        return invokeRead(name, arguments, dept, request.backend());
    }

    private Map<String, Object> invokeRead(String name, Map<String, Object> args, String dept, String backend) {
        log.info("fin tool name={} dept={} args={}", name, dept, PiiMask.mask(String.valueOf(args)));
        return pythonAiClient.invokeTool(name, args, dept, backend);
    }

    private static Map<String, Object> metricArgs(String companyCode, String concept, int year, String scope) {
        Map<String, Object> args = new LinkedHashMap<>();
        args.put("company_code", companyCode);
        args.put("concept", concept);
        args.put("year", year);
        args.put("scope", scope);
        return args;
    }

    private static void putIfPresent(Map<String, Object> args, String key, Object value) {
        if (value == null) {
            return;
        }
        if (value instanceof String text && text.isBlank()) {
            return;
        }
        args.put(key, value);
    }
}
