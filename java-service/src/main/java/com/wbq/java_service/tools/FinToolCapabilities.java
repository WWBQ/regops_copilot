package com.wbq.java_service.tools;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/** Java 侧自省：不经 Python，也不代理 RAG。 */
public final class FinToolCapabilities {

    private static final List<String> JAVA_TOOLS = List.of(
            "lookup_metric",
            "compare_peers",
            "list_scope",
            "verify_number",
            "create_review_draft"
    );

    private FinToolCapabilities() {
    }

    public static Map<String, Object> body() {
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("kind", "agent-capabilities");
        payload.put("owner", "java-service");
        payload.put("wired_to_chat", false);
        payload.put("rules", "docs/AGENT_RULES.md");
        payload.put("commands", JAVA_TOOLS.stream().map(FinToolCapabilities::command).toList());
        payload.put("forbidden", List.of(
                "execute_sql",
                "rag_search",
                "direct_http",
                "client_truncate",
                "invent_missing_metric",
                "compute_ratio"
        ));
        payload.put("must", List.of(
                "list_scope_before_unknown_company_or_concept",
                "stop_when_ok_false",
                "confirm_before_create_review_draft",
                "review_draft_pending_only",
                "stop_on_budget_exceeded",
                "maker_checker_via_java"
        ));
        return payload;
    }

    public static Map<String, Object> schema(String name) {
        if (name == null || !JAVA_TOOLS.contains(name)) {
            return null;
        }
        return command(name);
    }

    private static Map<String, Object> command(String name) {
        Map<String, Object> item = new LinkedHashMap<>();
        item.put("name", name);
        item.put("kind", "create_review_draft".equals(name) ? "write" : "read");
        item.put("description", description(name));
        item.put("inputSchema", inputSchema(name));
        return item;
    }

    private static String description(String name) {
        return switch (name) {
            case "lookup_metric" -> "按公司/年/口径取已通过数字。concepts 传 1–5 科，单科只放一个；缺数或待复核则该科 stop。";
            case "compare_peers" -> "同业只读并列查数，不手算差额或比率。";
            case "list_scope" -> "列出当前部门数据域内已入库的公司/年/指标。";
            case "verify_number" -> "把声称金额对回事实表；对不上就停。";
            case "create_review_draft" -> "创建 PENDING 审查工单草稿。须人工确认；不提交 maker-checker。";
            default -> name;
        };
    }

    private static Map<String, Object> inputSchema(String name) {
        Map<String, Object> schema = new LinkedHashMap<>();
        schema.put("type", "object");
        schema.put("additionalProperties", false);
        Map<String, Object> properties = new LinkedHashMap<>();
        switch (name) {
            case "lookup_metric" -> {
                properties.put("company_code", Map.of("type", "string", "pattern", "^\\d{6}$"));
                properties.put("year", Map.of("type", "integer", "minimum", 2000, "maximum", 2100));
                properties.put("scope", Map.of("type", "string", "default", "consolidated"));
                properties.put("concept", Map.of("type", "string"));
                properties.put("concepts", Map.of(
                        "type", "array",
                        "minItems", 1,
                        "maxItems", 5,
                        "items", Map.of("type", "string")
                ));
                schema.put("required", List.of("company_code", "year"));
            }
            case "verify_number" -> {
                properties.put("company_code", Map.of("type", "string", "pattern", "^\\d{6}$"));
                properties.put("concept", Map.of("type", "string"));
                properties.put("year", Map.of("type", "integer", "minimum", 2000, "maximum", 2100));
                properties.put("scope", Map.of("type", "string", "default", "consolidated"));
                properties.put("claimed", Map.of("type", "string"));
                schema.put("required", List.of("company_code", "concept", "year", "claimed"));
            }
            case "compare_peers" -> {
                properties.put("company_codes", Map.of(
                        "type", "array",
                        "minItems", 2,
                        "maxItems", 5,
                        "items", Map.of("type", "string", "pattern", "^\\d{6}$")
                ));
                properties.put("concept", Map.of("type", "string"));
                properties.put("year", Map.of("type", "integer", "minimum", 2000, "maximum", 2100));
                properties.put("scope", Map.of("type", "string", "default", "consolidated"));
                schema.put("required", List.of("company_codes", "concept", "year"));
            }
            case "list_scope" -> {
                properties.put("company_code", Map.of("type", "string", "pattern", "^\\d{6}$"));
                properties.put("year", Map.of("type", "integer"));
                properties.put("scope", Map.of("type", "string"));
                schema.put("required", List.of());
            }
            case "create_review_draft" -> {
                properties.put("company_code", Map.of("type", "string", "pattern", "^\\d{6}$"));
                properties.put("title", Map.of("type", "string"));
                properties.put("reason", Map.of("type", "string"));
                properties.put("company_codes", Map.of(
                        "type", "array",
                        "items", Map.of("type", "string", "pattern", "^\\d{6}$")
                ));
                properties.put("conclusion", Map.of("type", "string"));
                properties.put("clause_refs", Map.of("type", "array", "items", Map.of("type", "string")));
                properties.put("impact_scope", Map.of("type", "string"));
                properties.put("thread_id", Map.of("type", "string"));
                schema.put("required", List.of("company_code", "title", "reason"));
            }
            default -> {
            }
        }
        schema.put("properties", properties);
        return schema;
    }
}
