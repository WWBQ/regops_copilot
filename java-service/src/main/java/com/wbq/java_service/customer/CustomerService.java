package com.wbq.java_service.customer;

import java.util.List;
import java.util.UUID;

import com.wbq.java_service.auth.AuthSupport;
import com.wbq.java_service.auth.AuthUser;
import com.wbq.java_service.dto.customer.CustomerResponse;
import com.wbq.java_service.exception.BusinessException;
import com.wbq.java_service.identity.Role;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CustomerService {

    private final CustomerProfileRepository repository;

    public CustomerService(CustomerProfileRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public List<CustomerResponse> list() {
        AuthUser actor = AuthSupport.requireUser();
        return repository.findAllByOrderByCompanyCodeAsc().stream()
                .filter(item -> visible(actor, item))
                .map(CustomerService::toResponse)
                .toList();
    }

    @Transactional(readOnly = true)
    public CustomerResponse get(UUID publicId) {
        AuthUser actor = AuthSupport.requireUser();
        CustomerProfile profile = repository.findByPublicId(publicId)
                .orElseThrow(() -> BusinessException.notFound("客户档案不存在"));
        if (!visible(actor, profile)) {
            throw BusinessException.notFound("客户档案不存在");
        }
        return toResponse(profile);
    }

    static boolean visible(AuthUser actor, CustomerProfile profile) {
        if (actor.role() == Role.RM) {
            return "CLIENT".equals(profile.getClassification());
        }
        if (actor.role() == Role.ANALYST) {
            return profile.internalResearch() || actor.dept().equals(profile.getDept());
        }
        return true;
    }

    static CustomerResponse toResponse(CustomerProfile profile) {
        return new CustomerResponse(
                profile.getPublicId(),
                profile.getCompanyCode(),
                profile.getDisplayName(),
                profile.getClassification(),
                profile.getMaskedIdNo(),
                profile.getMaskedPhone(),
                profile.getRiskLevel(),
                profile.getNotes(),
                profile.getDept()
        );
    }
}
