package com.wbq.java_service.controller;

import java.util.List;
import java.util.UUID;

import com.wbq.java_service.customer.CustomerService;
import com.wbq.java_service.dto.customer.CustomerResponse;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/customers")
public class CustomerController {

    private final CustomerService customerService;

    public CustomerController(CustomerService customerService) {
        this.customerService = customerService;
    }

    @GetMapping
    @PreAuthorize("isAuthenticated()")
    public List<CustomerResponse> list() {
        return customerService.list();
    }

    @GetMapping("/{id}")
    @PreAuthorize("isAuthenticated()")
    public CustomerResponse get(@PathVariable UUID id) {
        return customerService.get(id);
    }
}
