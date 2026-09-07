package com.wbq.java_service.audit;

import com.wbq.java_service.auth.AuthUser;
import com.wbq.java_service.filter.RequestIdFilter;

import org.slf4j.MDC;
import org.springframework.stereotype.Service;

@Service
public class AuditService {

    private final AuditEventRepository repository;

    public AuditService(AuditEventRepository repository) {
        this.repository = repository;
    }

    public AuditEvent record(
            AuthUser actor,
            String action,
            String entityType,
            String entityId,
            String reason,
            String inputSummary,
            String beforeJson,
            String afterJson
    ) {
        AuditEvent event = new AuditEvent();
        event.setActorUsername(actor.username());
        event.setActorRole(actor.role().name());
        event.setDept(actor.dept());
        event.setAction(action);
        event.setEntityType(entityType);
        event.setEntityId(entityId);
        event.setRequestId(MDC.get(RequestIdFilter.MDC_KEY));
        event.setReason(reason == null ? "" : reason);
        event.setInputSummary(inputSummary == null ? "" : inputSummary);
        event.setBeforeJson(beforeJson == null ? "" : beforeJson);
        event.setAfterJson(afterJson == null ? "" : afterJson);
        return repository.save(event);
    }
}
