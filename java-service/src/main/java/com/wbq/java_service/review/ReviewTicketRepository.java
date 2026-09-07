package com.wbq.java_service.review;

import java.util.List;
import java.util.Optional;
import java.util.UUID;

import org.springframework.data.jpa.repository.JpaRepository;

public interface ReviewTicketRepository extends JpaRepository<ReviewTicket, Long> {
    Optional<ReviewTicket> findByPublicId(UUID publicId);

    Optional<ReviewTicket> findByIdempotencyKey(String idempotencyKey);

    Optional<ReviewTicket> findByThreadId(String threadId);

    List<ReviewTicket> findByDeptOrderByUpdatedAtDesc(String dept);

    List<ReviewTicket> findByDeptAndStatusOrderByUpdatedAtDesc(String dept, TicketStatus status);

    List<ReviewTicket> findAllByOrderByUpdatedAtDesc();

    List<ReviewTicket> findByStatusOrderByUpdatedAtDesc(TicketStatus status);
}
