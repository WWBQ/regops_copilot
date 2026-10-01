package com.wbq.java_service.controller;

import java.util.Map;

import com.wbq.java_service.client.PythonAiClient;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
class OpsProxyControllerTest {

    @Autowired
    private MockMvc mvc;

    @MockitoBean
    private PythonAiClient pythonAiClient;

    @Test
    void postIngestForwardsMultipart() throws Exception {
        when(pythonAiClient.startPdfIngest(any(), eq("002594_2024"), eq(true)))
                .thenReturn(Map.of(
                        "job_id", "11111111-1111-1111-1111-111111111111",
                        "doc_id", "002594_2024",
                        "status", "PENDING"
                ));
        MockMultipartFile file = new MockMultipartFile(
                "file",
                "002594_2024.pdf",
                MediaType.APPLICATION_PDF_VALUE,
                "%PDF-1.4 demo".getBytes()
        );
        mvc.perform(multipart("/api/ops/ingest")
                        .file(file)
                        .param("doc_id", "002594_2024")
                        .param("use_parse_cache", "true"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.job_id").value("11111111-1111-1111-1111-111111111111"))
                .andExpect(jsonPath("$.doc_id").value("002594_2024"));
        verify(pythonAiClient).startPdfIngest(any(), eq("002594_2024"), eq(true));
    }

    @Test
    void getIngestJobForwards() throws Exception {
        when(pythonAiClient.getIngestJob("11111111-1111-1111-1111-111111111111"))
                .thenReturn(Map.of(
                        "job_id", "11111111-1111-1111-1111-111111111111",
                        "status", "DONE",
                        "target_doc_id", "002594_2024"
                ));
        mvc.perform(get("/api/ops/ingest/jobs/11111111-1111-1111-1111-111111111111"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("DONE"));
    }

    @Test
    void performanceTracesForwardPagination() throws Exception {
        when(pythonAiClient.listPerformanceTraces(20, 5))
                .thenReturn(Map.of("total", 1, "items", java.util.List.of()));

        mvc.perform(get("/api/ops/performance-traces")
                        .param("limit", "20")
                        .param("offset", "5"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.total").value(1));

        verify(pythonAiClient).listPerformanceTraces(20, 5);
    }
}
