package com.wbq.java_service.identity;

import java.util.List;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.dao.DataAccessException;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Component;

import com.wbq.java_service.config.AppProperties;

@Component
public class DataSeeder implements ApplicationRunner {

    private static final Logger log = LoggerFactory.getLogger(DataSeeder.class);

    private final AppUserRepository users;
    private final PasswordEncoder passwordEncoder;
    private final AppProperties properties;

    public DataSeeder(AppUserRepository users, PasswordEncoder passwordEncoder, AppProperties properties) {
        this.users = users;
        this.passwordEncoder = passwordEncoder;
        this.properties = properties;
    }

    @Override
    public void run(ApplicationArguments args) {
        if (!properties.auth().seedEnabled()) {
            return;
        }
        try {
            seed("analyst", "analyst123", "投研分析师", "analyst@regops.local", Role.ANALYST, "research");
            seed("checker", "checker123", "合规复核员", "checker@regops.local", Role.CHECKER, "compliance");
            seed("rm", "rm123", "客户经理", "rm@regops.local", Role.RM, "rm");
            seed("admin", "admin123", "系统管理员", "admin@regops.local", Role.ADMIN, "compliance");
        } catch (DataAccessException ex) {
            log.warn("skip user seed (run docs/sql/w7_identity.sql): {}", ex.getMessage());
        }
    }

    private void seed(String username, String password, String displayName, String email, Role role, String dept) {
        if (users.existsByUsername(username)) {
            return;
        }
        AppUser user = new AppUser();
        user.setUsername(username);
        user.setPasswordHash(passwordEncoder.encode(password));
        user.setDisplayName(displayName);
        user.setEmail(email);
        user.setRole(role);
        user.setDept(dept);
        users.save(user);
        log.info("seeded user {} role={} dept={}", username, role, dept);
    }

    public static List<String> demoAccounts() {
        return List.of("analyst/analyst123", "checker/checker123", "rm/rm123", "admin/admin123");
    }
}
