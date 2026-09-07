package com.wbq.java_service.review;

import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

import com.wbq.java_service.audit.AuditService;
import com.wbq.java_service.auth.AuthSupport;
import com.wbq.java_service.auth.AuthUser;
import com.wbq.java_service.dto.review.CreateTicketRequest;
import com.wbq.java_service.dto.review.TicketResponse;
import com.wbq.java_service.exception.BusinessException;
import com.wbq.java_service.filter.RequestIdFilter;
import com.wbq.java_service.identity.Role;
import com.wbq.java_service.tools.DeptAcl;

import org.slf4j.MDC;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.orm.ObjectOptimisticLockingFailureException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ReviewService {

    private final ReviewTicketRepository tickets;
    private final AuditService auditService;
    private final ReviewTxGuard txGuard;

    public ReviewService(ReviewTicketRepository tickets, AuditService auditService, ReviewTxGuard txGuard) {
        this.tickets = tickets;
        this.auditService = auditService;
        this.txGuard = txGuard;
    }

    @Transactional
    public TicketResponse create(CreateTicketRequest request, String idempotencyKey) {
        AuthUser actor = requireSubmitter();
        DeptAcl.requireCompany(actor.dept(), request.companyCode());
        List<String> codes = request.companyCodes() == null || request.companyCodes().isEmpty()
                ? List.of(request.companyCode())
                : request.companyCodes();
        DeptAcl.requireCompanies(actor.dept(), codes);
        String key = firstNonBlank(idempotencyKey, request.threadId());
        if (key != null) {
            var existing = tickets.findByIdempotencyKey(key);
            if (existing.isPresent()) {
                return toResponse(existing.get(), true);
            }
        }
        if (request.threadId() != null && !request.threadId().isBlank()) {
            var byThread = tickets.findByThreadId(request.threadId().strip());
            if (byThread.isPresent()) {
                return toResponse(byThread.get(), true);
            }
        }
        ReviewTicket ticket = new ReviewTicket();
        ticket.setDept(actor.dept());
        ticket.setCompanyCode(request.companyCode());
        ticket.setCompanyCodes(new ArrayList<>(codes));
        ticket.setTitle(request.title());
        ticket.setReason(request.reason());
        ticket.setConclusion(request.conclusion());
        ticket.setRiskLevel(request.riskLevel());
        ticket.setClauseRefs(request.clauseRefs());
        ticket.setEvidenceQuotes(request.evidenceQuotes());
        ticket.setImpactScope(request.impactScope());
        ticket.setThreadId(request.threadId());
        ticket.setIdempotencyKey(key);
        ticket.setRequestId(MDC.get(RequestIdFilter.MDC_KEY));
        ticket.setInputSummary(summarize(request));
        ticket.setStatus(TicketStatus.PENDING);
        try {
            tickets.saveAndFlush(ticket);
        } catch (DataIntegrityViolationException ex) {
            if (key != null) {
                var byKey = tickets.findByIdempotencyKey(key);
                if (byKey.isPresent()) {
                    return toResponse(byKey.get(), true);
                }
            }
            if (request.threadId() != null && !request.threadId().isBlank()) {
                var byThread = tickets.findByThreadId(request.threadId().strip());
                if (byThread.isPresent()) {
                    return toResponse(byThread.get(), true);
                }
            }
            throw ex;
        }
        auditService.record(
                actor,
                "CREATE_TICKET",
                "review_ticket",
                ticket.getPublicId().toString(),
                request.reason(),
                ticket.getInputSummary(),
                "",
                ticket.snapshot()
        );
        txGuard.afterWrite();
        return toResponse(ticket, false);
    }

    @Transactional
    public TicketResponse submit(UUID publicId) {
        AuthUser actor = requireSubmitter();
        ReviewTicket ticket = loadVisible(publicId, actor);
        if (ticket.getStatus() == TicketStatus.SUBMITTED && actor.username().equals(ticket.getSubmittedBy())) {
            return toResponse(ticket, true);
        }
        if (ticket.getStatus() != TicketStatus.PENDING) {
            throw BusinessException.invalidState("只有 PENDING 草稿可以提交，当前是 " + ticket.getStatus());
        }
        String before = ticket.snapshot();
        ticket.setStatus(TicketStatus.SUBMITTED);
        ticket.setSubmittedBy(actor.username());
        tickets.saveAndFlush(ticket);
        auditService.record(
                actor,
                "SUBMIT_TICKET",
                "review_ticket",
                ticket.getPublicId().toString(),
                ticket.getReason(),
                ticket.getInputSummary(),
                before,
                ticket.snapshot()
        );
        txGuard.afterWrite();
        return toResponse(ticket, false);
    }

    @Transactional
    public TicketResponse decide(UUID publicId, boolean approve, String reason) {
        AuthUser actor = AuthSupport.requireUser();
        if (!actor.role().canReview()) {
            throw BusinessException.unauthorized("客户经理或无复核角色不能复核");
        }
        ReviewTicket ticket = loadVisible(publicId, actor);
        if (ticket.getStatus().isTerminal()) {
            throw BusinessException.invalidState("工单已结束，状态不能倒流");
        }
        if (ticket.getStatus() != TicketStatus.SUBMITTED) {
            throw BusinessException.invalidState("只有 SUBMITTED 工单可以复核");
        }
        if (actor.username().equals(ticket.getSubmittedBy())) {
            throw new BusinessException(
                    org.springframework.http.HttpStatus.FORBIDDEN,
                    "self_review",
                    "复核人不能等于提交人"
            );
        }
        String before = ticket.snapshot();
        try {
            ticket.setStatus(approve ? TicketStatus.REVIEWED : TicketStatus.REJECTED);
            ticket.setReviewedBy(actor.username());
            ticket.setReviewReason(reason);
            tickets.saveAndFlush(ticket);
        } catch (ObjectOptimisticLockingFailureException ex) {
            throw BusinessException.conflict("并发复核仅允许一次成功");
        }
        auditService.record(
                actor,
                approve ? "APPROVE_TICKET" : "REJECT_TICKET",
                "review_ticket",
                ticket.getPublicId().toString(),
                reason,
                ticket.getInputSummary(),
                before,
                ticket.snapshot()
        );
        txGuard.afterWrite();
        return toResponse(ticket, false);
    }

    @Transactional(readOnly = true)
    public List<TicketResponse> list(TicketStatus status) {
        AuthUser actor = AuthSupport.requireUser();
        if (actor.role().isRm()) {
            throw BusinessException.unauthorized("客户经理不能查看复核工单");
        }
        List<ReviewTicket> rows;
        if (actor.role() == Role.ANALYST) {
            rows = status == null
                    ? tickets.findByDeptOrderByUpdatedAtDesc(actor.dept())
                    : tickets.findByDeptAndStatusOrderByUpdatedAtDesc(actor.dept(), status);
        } else {
            rows = status == null
                    ? tickets.findAllByOrderByUpdatedAtDesc()
                    : tickets.findByStatusOrderByUpdatedAtDesc(status);
        }
        return rows.stream().map(item -> toResponse(item, false)).toList();
    }

    @Transactional(readOnly = true)
    public TicketResponse get(UUID publicId) {
        AuthUser actor = AuthSupport.requireUser();
        return toResponse(loadVisible(publicId, actor), false);
    }

    private ReviewTicket loadVisible(UUID publicId, AuthUser actor) {
        ReviewTicket ticket = tickets.findByPublicId(publicId)
                .orElseThrow(() -> BusinessException.notFound("工单不存在"));
        if (actor.role().isRm()) {
            throw BusinessException.notFound("工单不存在");
        }
        if (actor.role() == Role.ANALYST && !actor.dept().equals(ticket.getDept())) {
            throw BusinessException.notFound("工单不存在");
        }
        return ticket;
    }

    private static AuthUser requireSubmitter() {
        AuthUser actor = AuthSupport.requireUser();
        if (actor.role() == Role.RM || !actor.role().canSubmit()) {
            throw BusinessException.unauthorized("客户经理不能提交复核工单");
        }
        return actor;
    }

    private static String summarize(CreateTicketRequest request) {
        return request.companyCode() + " · " + request.title();
    }

    private static String firstNonBlank(String... values) {
        if (values == null) {
            return null;
        }
        for (String value : values) {
            if (value != null && !value.isBlank()) {
                return value.strip();
            }
        }
        return null;
    }

    static TicketResponse toResponse(ReviewTicket ticket, boolean replayed) {
        return new TicketResponse(
                ticket.getPublicId(),
                ticket.getStatus(),
                ticket.getDept(),
                ticket.getCompanyCode(),
                ticket.getCompanyCodes(),
                ticket.getTitle(),
                ticket.getReason(),
                ticket.getConclusion(),
                ticket.getRiskLevel(),
                ticket.getClauseRefs(),
                ticket.getImpactScope(),
                ticket.getThreadId(),
                ticket.getSubmittedBy(),
                ticket.getReviewedBy(),
                ticket.getReviewReason(),
                ticket.getInputSummary(),
                replayed,
                ticket.getCreatedAt(),
                ticket.getUpdatedAt()
        );
    }
}
