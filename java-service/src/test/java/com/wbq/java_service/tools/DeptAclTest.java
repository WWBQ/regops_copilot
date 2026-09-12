package com.wbq.java_service.tools;

import com.wbq.java_service.exception.ToolAccessException;

import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class DeptAclTest {

    @Test
    void missingDeptIsForbidden() {
        ToolAccessException ex = assertThrows(ToolAccessException.class, () -> DeptAcl.requireDept(null));
        assertEquals(HttpStatus.FORBIDDEN, ex.getStatus());
        assertEquals("unauthorized", ex.getErrorCode());
    }

    @Test
    void researchCannotReadMidea() {
        ToolAccessException ex = assertThrows(
                ToolAccessException.class,
                () -> DeptAcl.requireCompany("research", "000333")
        );
        assertEquals("unauthorized", ex.getErrorCode());
    }

    @Test
    void rmCannotReadByd() {
        ToolAccessException ex = assertThrows(
                ToolAccessException.class,
                () -> DeptAcl.requireCompany("rm", "002594")
        );
        assertEquals("unauthorized", ex.getErrorCode());
    }

    @Test
    void rmCanReadMidea() {
        DeptAcl.requireCompany("rm", "000333");
    }

    @Test
    void complianceCanReadCatl() {
        DeptAcl.requireCompany("compliance", "300750");
    }

    @Test
    void researchCannotReadCatl() {
        ToolAccessException ex = assertThrows(
                ToolAccessException.class,
                () -> DeptAcl.requireCompany("research", "300750")
        );
        assertEquals("unauthorized", ex.getErrorCode());
    }

    @Test
    void illegalCompanyCodeIs400() {
        ToolAccessException ex = assertThrows(
                ToolAccessException.class,
                () -> DeptAcl.requireCompany("compliance", "BYD")
        );
        assertEquals(HttpStatus.BAD_REQUEST, ex.getStatus());
        assertEquals("invalid_params", ex.getErrorCode());
    }
}
