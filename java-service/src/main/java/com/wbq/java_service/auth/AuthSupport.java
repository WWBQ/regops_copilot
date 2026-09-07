package com.wbq.java_service.auth;

import com.wbq.java_service.exception.BusinessException;
import com.wbq.java_service.identity.Role;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;

public final class AuthSupport {

    private AuthSupport() {
    }

    public static AuthUser currentOrNull() {
        Authentication authentication = SecurityContextHolder.getContext().getAuthentication();
        if (authentication == null || !(authentication.getPrincipal() instanceof AuthUser user)) {
            return null;
        }
        return user;
    }

    public static AuthUser requireUser() {
        AuthUser user = currentOrNull();
        if (user == null) {
            throw BusinessException.unauthorized("未登录");
        }
        return user;
    }

    public static String resolveDept(String headerDept) {
        AuthUser user = currentOrNull();
        if (user != null) {
            if (headerDept != null && !headerDept.isBlank() && !user.dept().equalsIgnoreCase(headerDept.strip())) {
                throw BusinessException.unauthorized("不能冒用其他部门");
            }
            return user.dept();
        }
        return headerDept;
    }

    public static boolean isRm() {
        AuthUser user = currentOrNull();
        return user != null && user.role() == Role.RM;
    }
}
