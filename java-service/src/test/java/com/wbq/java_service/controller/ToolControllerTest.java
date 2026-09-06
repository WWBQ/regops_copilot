package com.wbq.java_service.controller;

import java.util.Map;

import com.wbq.java_service.client.PythonAiClient;

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
    void reviewDraftRefusesWrite() throws Exception {
        mvc.perform(post("/api/tools/review-draft")
                        .header("X-Regops-Dept", "compliance")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"company_code\":\"002594\",\"title\":\"关联交易\",\"reason\":\"需复核\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.ok").value(false))
                .andExpect(jsonPath("$.stop").value(true))
                .andExpect(jsonPath("$.error_code").value("forbidden_write"));
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
                .andExpect(jsonPath("$.forbidden[0]").exists());
        mvc.perform(get("/api/tools/schema/lookup_metric"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.name").value("lookup_metric"));
        mvc.perform(get("/api/tools/schema/rag_search"))
                .andExpect(status().isNotFound());
    }
}
