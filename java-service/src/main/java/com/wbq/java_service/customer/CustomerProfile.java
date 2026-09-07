package com.wbq.java_service.customer;

import java.time.Instant;
import java.util.UUID;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "customer_profile")
public class CustomerProfile {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "public_id", nullable = false, unique = true)
    private UUID publicId;

    @Column(name = "company_code", nullable = false, length = 6)
    private String companyCode;

    @Column(name = "display_name", nullable = false, length = 80)
    private String displayName;

    @Column(nullable = false, length = 32)
    private String classification;

    @Column(name = "masked_id_no", nullable = false, length = 32)
    private String maskedIdNo;

    @Column(name = "masked_phone", nullable = false, length = 32)
    private String maskedPhone;

    @Column(name = "risk_level", nullable = false, length = 8)
    private String riskLevel;

    @Column(nullable = false)
    private String notes;

    @Column(nullable = false, length = 32)
    private String dept;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    public UUID getPublicId() {
        return publicId;
    }

    public String getCompanyCode() {
        return companyCode;
    }

    public String getDisplayName() {
        return displayName;
    }

    public String getClassification() {
        return classification;
    }

    public String getMaskedIdNo() {
        return maskedIdNo;
    }

    public String getMaskedPhone() {
        return maskedPhone;
    }

    public String getRiskLevel() {
        return riskLevel;
    }

    public String getNotes() {
        return notes;
    }

    public String getDept() {
        return dept;
    }

    public boolean internalResearch() {
        return "INTERNAL_RESEARCH".equals(classification);
    }
}
