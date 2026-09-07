package com.wbq.java_service.auth;

import com.wbq.java_service.config.AppProperties;
import com.wbq.java_service.dto.auth.LoginResponse;
import com.wbq.java_service.dto.auth.UserResponse;
import com.wbq.java_service.exception.BusinessException;
import com.wbq.java_service.identity.AppUser;
import com.wbq.java_service.identity.AppUserRepository;

import org.springframework.http.HttpStatus;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;

@Service
public class AuthService {

    private final AppUserRepository users;
    private final PasswordEncoder passwordEncoder;
    private final JwtService jwtService;
    private final AppProperties properties;

    public AuthService(
            AppUserRepository users,
            PasswordEncoder passwordEncoder,
            JwtService jwtService,
            AppProperties properties
    ) {
        this.users = users;
        this.passwordEncoder = passwordEncoder;
        this.jwtService = jwtService;
        this.properties = properties;
    }

    public LoginResponse login(String username, String password) {
        AppUser user = users.findByUsername(username)
                .orElseThrow(() -> new BusinessException(HttpStatus.UNAUTHORIZED, "unauthorized", "用户名或密码错误"));
        if (!user.isEnabled() || !passwordEncoder.matches(password, user.getPasswordHash())) {
            throw new BusinessException(HttpStatus.UNAUTHORIZED, "unauthorized", "用户名或密码错误");
        }
        return new LoginResponse(
                jwtService.issue(user),
                "Bearer",
                properties.auth().ttlSeconds(),
                toUser(user)
        );
    }

    public static UserResponse toUser(AppUser user) {
        return new UserResponse(
                user.getPublicId().toString(),
                user.getUsername(),
                user.getDisplayName(),
                user.getEmail(),
                user.getRole().name(),
                user.getDept()
        );
    }

    public static UserResponse toUser(AuthUser user) {
        return new UserResponse(
                user.publicId().toString(),
                user.username(),
                user.displayName(),
                user.email(),
                user.role().name(),
                user.dept()
        );
    }
}
