package com.wbq.java_service.identity;

public enum Role {
    ANALYST,
    CHECKER,
    RM,
    ADMIN;

    public String authority() {
        return "ROLE_" + name();
    }

    public boolean canReview() {
        return this == CHECKER || this == ADMIN;
    }

    public boolean canSubmit() {
        return this == ANALYST || this == CHECKER || this == ADMIN;
    }

    public boolean isRm() {
        return this == RM;
    }
}
