package com.wbq.java_service.dto.customer;

import java.util.UUID;

public record CustomerResponse(
        UUID id,
        String companyCode,
        String displayName,
        String classification,
        String maskedIdNo,
        String maskedPhone,
        String riskLevel,
        String notes,
        String dept
) {
}
