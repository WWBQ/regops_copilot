package com.wbq.java_service.controller;

import java.util.List;

import com.wbq.java_service.audit.AuditEvent;
import com.wbq.java_service.audit.AuditEventRepository;
import com.wbq.java_service.auth.AuthSupport;
import com.wbq.java_service.dto.audit.AuditEventResponse;
import com.wbq.java_service.exception.BusinessException;
import com.wbq.java_service.identity.Role;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/audit")
public class AuditController {

    private final AuditEventRepository repository;

    public AuditController(AuditEventRepository repository) {
        this.repository = repository;
    }

    @GetMapping("/events")
    @PreAuthorize("hasAnyRole('CHECKER','ADMIN','ANALYST')")
    public List<AuditEventResponse> list(
            @RequestParam(required = false) String entityType,
            @RequestParam(required = false) String entityId
    ) {
        var actor = AuthSupport.requireUser();
        if (actor.role() == Role.RM) {
            throw BusinessException.unauthorized("客户经理不能查看审计");
        }
        List<AuditEvent> rows;
        if (entityType != null && entityId != null) {
            rows = repository.findByEntityTypeAndEntityIdOrderByOccurredAtDesc(entityType, entityId);
        } else {
            rows = repository.findTop100ByOrderByOccurredAtDesc();
        }
        return rows.stream().map(AuditController::toResponse).toList();
    }

    private static AuditEventResponse toResponse(AuditEvent event) {
        return new AuditEventResponse(
                event.getId(),
                event.getOccurredAt(),
                event.getActorUsername(),
                event.getActorRole(),
                event.getDept(),
                event.getAction(),
                event.getEntityType(),
                event.getEntityId(),
                event.getRequestId(),
                event.getReason(),
                event.getInputSummary(),
                event.getBeforeJson(),
                event.getAfterJson()
        );
    }
}
