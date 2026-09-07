package com.wbq.java_service.review;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;

@Entity
@Table(name = "review_draft")
public class ReviewTicket {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "public_id", nullable = false, unique = true)
    private UUID publicId = UUID.randomUUID();

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 16)
    private TicketStatus status = TicketStatus.PENDING;

    @Column(nullable = false, length = 32)
    private String dept;

    @Column(name = "company_code", nullable = false, length = 6)
    private String companyCode;

    @JdbcTypeCode(SqlTypes.JSON)
    @Column(name = "company_codes", nullable = false)
    private List<String> companyCodes = new ArrayList<>();

    @Column(nullable = false, length = 120)
    private String title;

    @Column(nullable = false)
    private String reason;

    @Column(nullable = false)
    private String conclusion = "";

    @Column(name = "risk_level", length = 8)
    private String riskLevel;

    @JdbcTypeCode(SqlTypes.JSON)
    @Column(name = "clause_refs", nullable = false)
    private List<String> clauseRefs = new ArrayList<>();

    @JdbcTypeCode(SqlTypes.JSON)
    @Column(name = "evidence_quotes", nullable = false)
    private List<String> evidenceQuotes = new ArrayList<>();

    @Column(name = "impact_scope", nullable = false)
    private String impactScope = "";

    @Column(name = "thread_id", length = 80)
    private String threadId;

    @Column(name = "request_id", length = 64)
    private String requestId;

    @Column(name = "idempotency_key", length = 128)
    private String idempotencyKey;

    @Column(name = "submitted_by", length = 64)
    private String submittedBy;

    @Column(name = "reviewed_by", length = 64)
    private String reviewedBy;

    @Column(name = "review_reason")
    private String reviewReason;

    @Column(name = "input_summary")
    private String inputSummary;

    @Version
    @Column(nullable = false)
    private Long version;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt = Instant.now();

    @Column(name = "updated_at", nullable = false)
    private Instant updatedAt = Instant.now();

    public Long getId() {
        return id;
    }

    public UUID getPublicId() {
        return publicId;
    }

    public TicketStatus getStatus() {
        return status;
    }

    public void setStatus(TicketStatus status) {
        this.status = status;
        this.updatedAt = Instant.now();
    }

    public String getDept() {
        return dept;
    }

    public void setDept(String dept) {
        this.dept = dept;
    }

    public String getCompanyCode() {
        return companyCode;
    }

    public void setCompanyCode(String companyCode) {
        this.companyCode = companyCode;
    }

    public List<String> getCompanyCodes() {
        return companyCodes;
    }

    public void setCompanyCodes(List<String> companyCodes) {
        this.companyCodes = companyCodes == null ? new ArrayList<>() : new ArrayList<>(companyCodes);
    }

    public String getTitle() {
        return title;
    }

    public void setTitle(String title) {
        this.title = title;
    }

    public String getReason() {
        return reason;
    }

    public void setReason(String reason) {
        this.reason = reason;
    }

    public String getConclusion() {
        return conclusion;
    }

    public void setConclusion(String conclusion) {
        this.conclusion = conclusion == null ? "" : conclusion;
    }

    public String getRiskLevel() {
        return riskLevel;
    }

    public void setRiskLevel(String riskLevel) {
        this.riskLevel = riskLevel;
    }

    public List<String> getClauseRefs() {
        return clauseRefs;
    }

    public void setClauseRefs(List<String> clauseRefs) {
        this.clauseRefs = clauseRefs == null ? new ArrayList<>() : new ArrayList<>(clauseRefs);
    }

    public List<String> getEvidenceQuotes() {
        return evidenceQuotes;
    }

    public void setEvidenceQuotes(List<String> evidenceQuotes) {
        this.evidenceQuotes = evidenceQuotes == null ? new ArrayList<>() : new ArrayList<>(evidenceQuotes);
    }

    public String getImpactScope() {
        return impactScope;
    }

    public void setImpactScope(String impactScope) {
        this.impactScope = impactScope == null ? "" : impactScope;
    }

    public String getThreadId() {
        return threadId;
    }

    public void setThreadId(String threadId) {
        this.threadId = threadId;
    }

    public String getRequestId() {
        return requestId;
    }

    public void setRequestId(String requestId) {
        this.requestId = requestId;
    }

    public String getIdempotencyKey() {
        return idempotencyKey;
    }

    public void setIdempotencyKey(String idempotencyKey) {
        this.idempotencyKey = idempotencyKey;
    }

    public String getSubmittedBy() {
        return submittedBy;
    }

    public void setSubmittedBy(String submittedBy) {
        this.submittedBy = submittedBy;
    }

    public String getReviewedBy() {
        return reviewedBy;
    }

    public void setReviewedBy(String reviewedBy) {
        this.reviewedBy = reviewedBy;
    }

    public String getReviewReason() {
        return reviewReason;
    }

    public void setReviewReason(String reviewReason) {
        this.reviewReason = reviewReason;
    }

    public String getInputSummary() {
        return inputSummary;
    }

    public void setInputSummary(String inputSummary) {
        this.inputSummary = inputSummary;
    }

    public Long getVersion() {
        return version;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }

    public Instant getUpdatedAt() {
        return updatedAt;
    }

    public String snapshot() {
        return status + "|" + (submittedBy == null ? "" : submittedBy) + "|" + (reviewedBy == null ? "" : reviewedBy);
    }
}
