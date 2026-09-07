package com.wbq.java_service.review;

public enum TicketStatus {
    PENDING,
    SUBMITTED,
    REVIEWED,
    REJECTED;

    public boolean isTerminal() {
        return this == REVIEWED || this == REJECTED;
    }
}
