package com.wbq.java_service.tools;

import java.util.Collection;
import java.util.Set;

import com.wbq.java_service.exception.ToolAccessException;

import org.springframework.http.HttpStatus;

/**
 * 部门数据域。与 Python mock {@code DEPT_ALLOW} 对齐。
 * Java 工具入口必须带部门；缺部门即 403。
 */
public final class DeptAcl {

    public static final Set<String> RESEARCH = Set.of("002594", "601633");
    public static final Set<String> COMPLIANCE = Set.of("002594", "601633", "000333", "000651", "600031");
    public static final Set<String> RM = Set.of("000333", "000651");

    private DeptAcl() {
    }

    public static void requireDept(String dept) {
        if (dept == null || dept.isBlank()) {
            throw new ToolAccessException("unauthorized", "缺少部门：X-Regops-Dept");
        }
        if (!"research".equals(dept) && !"compliance".equals(dept) && !"rm".equals(dept)) {
            throw new ToolAccessException("unauthorized", "未知部门 " + dept);
        }
    }

    public static void requireCompany(String dept, String companyCode) {
        requireDept(dept);
        requireCompanyCode(companyCode);
        if (!allowlist(dept).contains(companyCode)) {
            throw new ToolAccessException("unauthorized", "部门 " + dept + " 不能查询 " + companyCode);
        }
    }

    public static void requireCompanies(String dept, Collection<String> companyCodes) {
        if (companyCodes == null || companyCodes.isEmpty()) {
            throw new ToolAccessException(HttpStatus.BAD_REQUEST, "invalid_params", "company_codes 不能为空");
        }
        for (String companyCode : companyCodes) {
            requireCompany(dept, companyCode);
        }
    }

    public static void requireCompanyCode(String companyCode) {
        if (companyCode == null || !companyCode.matches("\\d{6}")) {
            throw new ToolAccessException(HttpStatus.BAD_REQUEST, "invalid_params", "company_code 必须是 6 位证券代码");
        }
    }

    public static Set<String> allowlist(String dept) {
        if ("research".equals(dept)) {
            return RESEARCH;
        }
        if ("rm".equals(dept)) {
            return RM;
        }
        return COMPLIANCE;
    }
}
