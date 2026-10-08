package com.wbq.java_service.controller;

import java.math.BigDecimal;
import java.sql.Timestamp;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.format.DateTimeParseException;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.UUID;

import com.wbq.java_service.auth.AuthSupport;
import com.wbq.java_service.exception.BusinessException;
import com.wbq.java_service.identity.Role;
import com.wbq.java_service.security.DeptAcl;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/** 财务事实人工复核：来源字段只读，审批结果和修订前快照写入数据库。 */
@RestController
@RequestMapping("/api/quality")
public class FinancialFactReviewController {

    private final JdbcTemplate jdbc;

    public FinancialFactReviewController(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public record ReviewRequest(String decision, String reviewedValueYuan, String note, String expectedUpdatedAt) {}
    public record ReviewEntry(long id, String decision, String originalValueYuan, String reviewedValueYuan,
                              String originalStatus, String originalReason, String note, String sourceContentHash,
                              UUID reviewerId, String reviewerName, Instant createdAt) {}
    public record ReviewDetail(long metricId, String status, String valueYuan, String rawValue,
                               String reviewReason, Instant updatedAt, String companyCode, String docId,
                               String concept, String period, String sourceType, String contentHash,
                               Integer pageNo, String rawName, String unitRaw, String xbrlTag,
                               String statement, String scope, List<ReviewEntry> history) {}
    public record ReviewQueueItem(long id, String companyCode, String docId, String concept,
                                  String period, String valueYuan, String rawValue, String status,
                                  String reviewReason, Instant updatedAt) {}
    public record ReviewQueue(int total, List<ReviewQueueItem> items) {}

    private record Fact(long id, String companyCode, String status, BigDecimal valueYuan, String rawValue,
                        String reviewReason, String sourceType, String contentHash, Integer pageNo,
                        String bboxJson, Instant updatedAt, String docId, String concept, String period,
                        String rawName, String unitRaw, String xbrlTag, String statement, String scope) {}

    @GetMapping("/reviews")
    public ReviewQueue queue(@RequestParam(defaultValue = "pending") String view,
                             @RequestParam(defaultValue = "0") int offset) {
        if (!List.of("pending", "reviewed").contains(view) || offset < 0) {
            throw BusinessException.badRequest("审核列表参数无效");
        }
        String dept = AuthSupport.requireUser().dept();
        DeptAcl.requireDept(dept);
        var allowed = DeptAcl.allowlist(dept).stream().sorted().toList();
        String markers = String.join(",", Collections.nCopies(allowed.size(), "?"));
        String where = " WHERE status " + ("pending".equals(view)
                ? "= 'human_review'" : "IN ('manually_accepted', 'rejected')")
                + " AND company_code IN (" + markers + ")";
        var params = new ArrayList<Object>(allowed);
        Integer total = jdbc.queryForObject("SELECT COUNT(*) FROM fin_metric" + where, Integer.class, params.toArray());
        params.add(200);
        params.add(offset);
        List<ReviewQueueItem> items = jdbc.query("""
                SELECT id, company_code, doc_id, concept, period, value_yuan, raw_value,
                       status, review_reason, updated_at FROM fin_metric
                """ + where + " ORDER BY updated_at DESC, id DESC LIMIT ? OFFSET ?", (rs, row) -> new ReviewQueueItem(
                rs.getLong("id"), rs.getString("company_code"), rs.getString("doc_id"),
                rs.getString("concept"), rs.getString("period"), decimalText(rs.getBigDecimal("value_yuan")),
                rs.getString("raw_value"), rs.getString("status"), rs.getString("review_reason"),
                rs.getTimestamp("updated_at").toInstant()), params.toArray());
        return new ReviewQueue(total == null ? 0 : total, items);
    }

    @GetMapping("/facts/{metricId}/review")
    public ReviewDetail detail(@PathVariable long metricId) {
        Fact fact = findFact(metricId, false);
        requireCompanyAccess(fact.companyCode());
        return detailFor(fact);
    }

    @PostMapping("/facts/{metricId}/review")
    @Transactional
    public ReviewDetail review(@PathVariable long metricId, @RequestBody ReviewRequest request) {
        var reviewer = AuthSupport.requireUser();
        if (reviewer.role() == Role.RM) {
            throw BusinessException.unauthorized("当前角色不能复核财务事实");
        }
        if (request == null) {
            throw BusinessException.badRequest("缺少审核内容");
        }
        Fact fact = findFact(metricId, true);
        requireCompanyAccess(fact.companyCode());
        if (!"human_review".equals(fact.status())) {
            throw BusinessException.invalidState("只有待人工复核的事实可以操作，请刷新列表");
        }
        Instant expected;
        try {
            expected = OffsetDateTime.parse(request.expectedUpdatedAt()).toInstant();
        } catch (NullPointerException | DateTimeParseException ex) {
            throw BusinessException.badRequest("缺少或无效的事实更新时间");
        }
        if (!expected.equals(fact.updatedAt())) {
            throw BusinessException.conflict("事实已被重新入库或其他人修改，请刷新后再复核");
        }
        String note = request.note() == null ? "" : request.note().strip();
        if (note.length() < 10 || note.length() > 1000) {
            throw BusinessException.badRequest("核对依据须填写 10～1000 字");
        }
        boolean approve = "approve".equals(request.decision());
        if (!approve && !"reject".equals(request.decision())) {
            throw BusinessException.badRequest("复核决定只能是确认通过或拒绝");
        }
        BigDecimal reviewedValue = approve ? parseAmount(request.reviewedValueYuan()) : null;
        if (approve && !hasProvenance(fact)) {
            throw BusinessException.invalidState("缺少可回溯的来源哈希或 PDF 定位，不能确认通过");
        }

        String status = approve ? "manually_accepted" : "rejected";
        String reason = (approve ? "人工复核通过：" : "人工复核拒绝：") + note;
        jdbc.update("""
                INSERT INTO fin_metric_review (
                    metric_id, source_updated_at, original_value_yuan, original_status,
                    original_reason, reviewed_value_yuan, decision, note, source_content_hash,
                    reviewer_id, reviewer_name
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, metricId, Timestamp.from(fact.updatedAt()), fact.valueYuan(), fact.status(),
                fact.reviewReason(), reviewedValue, request.decision(), note, fact.contentHash(),
                reviewer.publicId(), reviewer.displayName());
        jdbc.update("""
                UPDATE fin_metric SET status = ?, value_yuan = ?, review_reason = ?, updated_at = NOW()
                WHERE id = ?
                """, status, approve ? reviewedValue : fact.valueYuan(), reason, metricId);
        return detailFor(findFact(metricId, false));
    }

    private Fact findFact(long metricId, boolean lock) {
        if (metricId < 1) throw BusinessException.badRequest("事实 ID 无效");
        String sql = """
                SELECT id, company_code, status, value_yuan, raw_value, review_reason,
                       source_type, content_hash, page_no, bbox_json::text AS bbox_json, updated_at,
                       doc_id, concept, period, raw_name, unit_raw, xbrl_tag, statement, scope
                FROM fin_metric WHERE id = ?
                """ + (lock ? " FOR UPDATE" : "");
        List<Fact> facts = jdbc.query(sql, (rs, row) -> new Fact(
                rs.getLong("id"), rs.getString("company_code"), rs.getString("status"),
                rs.getBigDecimal("value_yuan"), rs.getString("raw_value"), rs.getString("review_reason"),
                rs.getString("source_type"), rs.getString("content_hash"),
                rs.getObject("page_no", Integer.class), rs.getString("bbox_json"),
                rs.getTimestamp("updated_at").toInstant(), rs.getString("doc_id"),
                rs.getString("concept"), rs.getString("period"), rs.getString("raw_name"),
                rs.getString("unit_raw"), rs.getString("xbrl_tag"), rs.getString("statement"),
                rs.getString("scope")), metricId);
        if (facts.isEmpty()) throw BusinessException.notFound("财务事实不存在");
        return facts.getFirst();
    }

    private ReviewDetail detailFor(Fact fact) {
        List<ReviewEntry> history = jdbc.query("""
                SELECT id, decision, original_value_yuan, reviewed_value_yuan,
                       original_status, original_reason, note, source_content_hash,
                       reviewer_id, reviewer_name, created_at
                FROM fin_metric_review WHERE metric_id = ? ORDER BY created_at DESC, id DESC
                """, (rs, row) -> new ReviewEntry(
                rs.getLong("id"), rs.getString("decision"), decimalText(rs.getBigDecimal("original_value_yuan")),
                decimalText(rs.getBigDecimal("reviewed_value_yuan")), rs.getString("original_status"),
                rs.getString("original_reason"), rs.getString("note"), rs.getString("source_content_hash"),
                rs.getObject("reviewer_id", UUID.class), rs.getString("reviewer_name"),
                rs.getTimestamp("created_at").toInstant()), fact.id());
        return new ReviewDetail(fact.id(), fact.status(), decimalText(fact.valueYuan()),
                fact.rawValue(), fact.reviewReason(), fact.updatedAt(), fact.companyCode(), fact.docId(),
                fact.concept(), fact.period(), fact.sourceType(), fact.contentHash(), fact.pageNo(),
                fact.rawName(), fact.unitRaw(), fact.xbrlTag(), fact.statement(), fact.scope(), history);
    }

    private static void requireCompanyAccess(String companyCode) {
        DeptAcl.requireCompany(AuthSupport.requireUser().dept(), companyCode);
    }

    private static String decimalText(BigDecimal value) {
        return value == null ? null : value.toPlainString();
    }

    private static BigDecimal parseAmount(String text) {
        if (text == null || !text.matches("-?\\d{1,20}(?:\\.\\d{1,4})?")) {
            throw BusinessException.badRequest("修订金额必须是元，最多 20 位整数和 4 位小数");
        }
        return new BigDecimal(text);
    }

    private static boolean hasProvenance(Fact fact) {
        if (fact.contentHash() == null || !fact.contentHash().matches("sha256:[0-9a-f]{64}")) {
            return false;
        }
        if ("web".equals(fact.sourceType())) {
            return true;
        }
        return "pdf".equals(fact.sourceType()) && fact.pageNo() != null && fact.pageNo() > 0
                && fact.bboxJson() != null && !"null".equals(fact.bboxJson());
    }
}
