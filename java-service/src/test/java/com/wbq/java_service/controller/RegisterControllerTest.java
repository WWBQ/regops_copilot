package com.wbq.java_service.controller;

import com.wbq.java_service.auth.JwtService;
import com.wbq.java_service.identity.AppUser;
import com.wbq.java_service.identity.AppUserRepository;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.http.MediaType;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
class RegisterControllerTest {
    @Autowired MockMvc mvc;
    @MockitoBean AppUserRepository users;
    @MockitoBean JwtService jwtService;

    @Test
    void registrationAssignsFixedLeastPrivilegeScope() throws Exception {
        when(users.saveAndFlush(any(AppUser.class))).thenAnswer(invocation -> invocation.getArgument(0));
        when(jwtService.issue(any(AppUser.class))).thenReturn("test-token");
        mvc.perform(post("/api/auth/register")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                        {"username":"new_user","password":"safe-password-123",
                         "displayName":"新用户","email":"u@example.com",
                         "role":"ADMIN","dept":"compliance"}
                        """))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.user.role").value("ANALYST"))
                .andExpect(jsonPath("$.user.dept").value("research"));
    }
}
