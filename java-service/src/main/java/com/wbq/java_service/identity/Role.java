package com.wbq.java_service.identity;

public enum Role {
    ANALYST,
    CHECKER,
    RM,
    ADMIN;

    public String authority() {
        return "ROLE_" + name();
    }

    public boolean isRm() {
        return this == RM;
    }
}
