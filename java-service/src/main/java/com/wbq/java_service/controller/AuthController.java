package com.wbq.java_service.controller;

import com.wbq.java_service.auth.AuthService;
import com.wbq.java_service.auth.AuthSupport;
import com.wbq.java_service.dto.auth.LoginRequest;
import com.wbq.java_service.dto.auth.LoginResponse;
import com.wbq.java_service.dto.auth.UserResponse;
import com.wbq.java_service.identity.DataSeeder;

import jakarta.validation.Valid;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/auth")
public class AuthController {

    private final AuthService authService;

    public AuthController(AuthService authService) {
        this.authService = authService;
    }

    @PostMapping("/login")
    public LoginResponse login(@Valid @RequestBody LoginRequest request) {
        return authService.login(request.username(), request.password());
    }

    @GetMapping("/me")
    public UserResponse me() {
        return AuthService.toUser(AuthSupport.requireUser());
    }

    @GetMapping("/demo-accounts")
    public Object demoAccounts() {
        return java.util.Map.of("accounts", DataSeeder.demoAccounts());
    }
}
