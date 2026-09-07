package com.wbq.java_service.controller;

import java.util.List;
import java.util.UUID;

import com.wbq.java_service.dto.review.CreateTicketRequest;
import com.wbq.java_service.dto.review.DecideRequest;
import com.wbq.java_service.dto.review.TicketResponse;
import com.wbq.java_service.review.ReviewService;
import com.wbq.java_service.review.TicketStatus;

import jakarta.validation.Valid;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/reviews")
public class ReviewController {

    private final ReviewService reviewService;

    public ReviewController(ReviewService reviewService) {
        this.reviewService = reviewService;
    }

    @GetMapping("/tickets")
    @PreAuthorize("hasAnyRole('ANALYST','CHECKER','ADMIN')")
    public List<TicketResponse> list(@RequestParam(required = false) TicketStatus status) {
        return reviewService.list(status);
    }

    @GetMapping("/tickets/{id}")
    @PreAuthorize("hasAnyRole('ANALYST','CHECKER','ADMIN')")
    public TicketResponse get(@PathVariable UUID id) {
        return reviewService.get(id);
    }

    @PostMapping("/tickets")
    @PreAuthorize("hasAnyRole('ANALYST','CHECKER','ADMIN')")
    public TicketResponse create(
            @Valid @RequestBody CreateTicketRequest body,
            @RequestHeader(value = "Idempotency-Key", required = false) String idempotencyKey
    ) {
        return reviewService.create(body, idempotencyKey);
    }

    @PostMapping("/tickets/{id}/submit")
    @PreAuthorize("hasAnyRole('ANALYST','CHECKER','ADMIN')")
    public TicketResponse submit(@PathVariable UUID id) {
        return reviewService.submit(id);
    }

    @PostMapping("/tickets/{id}/approve")
    @PreAuthorize("hasAnyRole('CHECKER','ADMIN')")
    public TicketResponse approve(@PathVariable UUID id, @Valid @RequestBody DecideRequest body) {
        return reviewService.decide(id, true, body.reason());
    }

    @PostMapping("/tickets/{id}/reject")
    @PreAuthorize("hasAnyRole('CHECKER','ADMIN')")
    public TicketResponse reject(@PathVariable UUID id, @Valid @RequestBody DecideRequest body) {
        return reviewService.decide(id, false, body.reason());
    }
}
