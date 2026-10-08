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
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyList;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
@WithMockUser
class OpsProxyControllerTest {

    @Autowired
    private MockMvc mvc;

    @MockitoBean
    private PythonAiClient pythonAiClient;

    @Test
    void removedLogEventsEndpointIsNotAvailable() throws Exception {
        mvc.perform(get("/api/ops/logs/events"))
                .andExpect(status().isNotFound());
    }

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
    void batchMonitorForwardsPagination() throws Exception {
        when(pythonAiClient.listIngestBatches(20, 0, null, null, null))
                .thenReturn(Map.of("total", 1, "items", java.util.List.of()));
        mvc.perform(get("/api/ops/ingest/batches"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.total").value(1));
        verify(pythonAiClient).listIngestBatches(20, 0, null, null, null);
    }

    @Test
    void batchMonitorForwardsTaskFilters() throws Exception {
        when(pythonAiClient.listIngestBatches(20, 0, "FAILED", "mineru", "002594"))
                .thenReturn(Map.of("total", 0, "items", java.util.List.of()));
        mvc.perform(get("/api/ops/ingest/batches")
                        .param("status", "FAILED")
                        .param("parser_backend", "mineru")
                        .param("keyword", "002594"))
                .andExpect(status().isOk());
        verify(pythonAiClient).listIngestBatches(20, 0, "FAILED", "mineru", "002594");
    }

    @Test
    void batchCreateForwardsJson() throws Exception {
        when(pythonAiClient.startIngestBatch(any())).thenReturn(Map.of(
                "batch_id", "11111111-1111-1111-1111-111111111111", "total_files", 2
        ));
        mvc.perform(post("/api/ops/ingest/batches")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"doc_ids\":[\"a\",\"b\"]}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.total_files").value(2));
    }

    @Test
    void batchUploadForwardsMultipleFiles() throws Exception {
        when(pythonAiClient.uploadIngestBatch(anyList(), eq("年度批次"), eq("docling"), eq(true)))
                .thenReturn(Map.of("batch_id", "11111111-1111-1111-1111-111111111111", "total_files", 2));
        MockMultipartFile first = new MockMultipartFile(
                "files", "a.pdf", MediaType.APPLICATION_PDF_VALUE, "%PDF-1.4 a".getBytes());
        MockMultipartFile second = new MockMultipartFile(
                "files", "b.pdf", MediaType.APPLICATION_PDF_VALUE, "%PDF-1.4 b".getBytes());
        mvc.perform(multipart("/api/ops/ingest/batches/upload")
                        .file(first).file(second)
                        .param("title", "年度批次")
                        .param("parser_backend", "docling")
                        .param("use_parse_cache", "true"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.total_files").value(2));
        verify(pythonAiClient).uploadIngestBatch(anyList(), eq("年度批次"), eq("docling"), eq(true));
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
