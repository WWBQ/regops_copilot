package com.wbq.java_service.controller;

import java.util.List;
import java.util.Map;

import com.wbq.java_service.client.PythonAiClient;
import com.wbq.java_service.exception.PythonAiException;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.ArgumentMatchers.isNull;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
class ToolControllerTest {

    @Autowired
    private MockMvc mvc;

    @MockitoBean
    private PythonAiClient pythonAiClient;

    @Test
    void missingDeptIs403() throws Exception {
        mvc.perform(post("/api/tools/lookup")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"company_code\":\"002594\",\"concept\":\"revenue\",\"year\":2024}"))
                .andExpect(status().isForbidden())
                .andExpect(jsonPath("$.extra.error_code").value("unauthorized"));
        verifyNoInteractions(pythonAiClient);
    }

    @Test
    void researchCrossDeptIs403() throws Exception {
        mvc.perform(post("/api/tools/lookup")
                        .header("X-Regops-Dept", "research")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"company_code\":\"000333\",\"concept\":\"revenue\",\"year\":2024}"))
                .andExpect(status().isForbidden())
                .andExpect(jsonPath("$.extra.error_code").value("unauthorized"));
        verifyNoInteractions(pythonAiClient);
    }

    @Test
    void illegalYearIs400() throws Exception {
        mvc.perform(post("/api/tools/lookup")
                        .header("X-Regops-Dept", "compliance")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"company_code\":\"002594\",\"concept\":\"revenue\",\"year\":1999}"))
                .andExpect(status().isBadRequest());
        verifyNoInteractions(pythonAiClient);
    }

    @Test
    void researchOwnCompanyCallsPython() throws Exception {
        when(pythonAiClient.invokeTool(eq("lookup_metric"), any(), eq("research"), isNull()))
                .thenReturn(Map.of("ok", true, "stop", false, "name", "lookup_metric"));
        mvc.perform(post("/api/tools/lookup")
                        .header("X-Regops-Dept", "research")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"company_code\":\"002594\",\"concept\":\"revenue\",\"year\":2024}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.ok").value(true));
    }

    @Test
    void reviewDraftCallsPythonWrite() throws Exception {
        when(pythonAiClient.invokeToolWrite(eq("create_review_draft"), any(), eq("compliance"), isNull(), isNull()))
                .thenReturn(Map.of(
                        "ok", true,
                        "stop", false,
                        "name", "create_review_draft",
                        "result", Map.of("status", "PENDING", "draft_id", "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
                ));
        mvc.perform(post("/api/tools/review-draft")
                        .header("X-Regops-Dept", "compliance")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"company_code\":\"002594\",\"title\":\"关联交易\",\"reason\":\"需复核\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.ok").value(true));
    }

    @Test
    void reviewDraftMissingDeptIs403() throws Exception {
        mvc.perform(post("/api/tools/review-draft")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"company_code\":\"002594\",\"title\":\"关联交易\",\"reason\":\"需复核\"}"))
                .andExpect(status().isForbidden())
                .andExpect(jsonPath("$.extra.error_code").value("unauthorized"));
        verifyNoInteractions(pythonAiClient);
    }

    @Test
    void listReviewDraftsCallsPython() throws Exception {
        when(pythonAiClient.listReviewDrafts("research", 50, 0))
                .thenReturn(Map.of("items", List.of(), "total", 0, "dept", "research"));
        mvc.perform(get("/api/tools/review-drafts")
                        .header("X-Regops-Dept", "research"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.total").value(0));
    }

    @Test
    void getReviewDraftCrossDeptIs404() throws Exception {
        when(pythonAiClient.getReviewDraft("research", "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"))
                .thenThrow(new PythonAiException(404, "review draft not found"));
        mvc.perform(get("/api/tools/review-drafts/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
                        .header("X-Regops-Dept", "research"))
                .andExpect(status().isNotFound());
    }

    @Test
    void listReviewDraftsMissingDeptIs403() throws Exception {
        mvc.perform(get("/api/tools/review-drafts"))
                .andExpect(status().isForbidden())
                .andExpect(jsonPath("$.extra.error_code").value("unauthorized"));
        verifyNoInteractions(pythonAiClient);
    }

    @Test
    void invokeDoesNotProxyRag() throws Exception {
        mvc.perform(post("/api/tools/invoke")
                        .header("X-Regops-Dept", "compliance")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"name\":\"rag_search\",\"arguments\":{\"question\":\"风险\"}}"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.extra.error_code").value("invalid_params"));
        verifyNoInteractions(pythonAiClient);
    }

    @Test
    void capabilitiesAndUnknownSchema() throws Exception {
        mvc.perform(get("/api/tools/capabilities"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.kind").value("agent-capabilities"))
                .andExpect(jsonPath("$.forbidden[0]").exists())
                .andExpect(jsonPath("$.must[2]").value("confirm_before_create_review_draft"))
                .andExpect(jsonPath("$.must[4]").value("stop_on_budget_exceeded"));
        mvc.perform(get("/api/tools/schema/lookup_metric"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.name").value("lookup_metric"));
        mvc.perform(get("/api/tools/schema/rag_search"))
                .andExpect(status().isNotFound());
    }
}
