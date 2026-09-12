package com.wbq.java_service.controller;

import java.io.OutputStream;
import java.nio.charset.StandardCharsets;

import com.wbq.java_service.client.PythonAiClient;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.http.MediaType;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.nullable;
import static org.mockito.Mockito.doAnswer;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.asyncDispatch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.request;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
class ChatProxyControllerTest {

    @Autowired
    private MockMvc mvc;

    @MockitoBean
    private PythonAiClient pythonAiClient;

    @Test
    void chatStreamWritesSse() throws Exception {
        doAnswer(invocation -> {
            OutputStream out = invocation.getArgument(1);
            out.write("event: done\ndata: {\"reply\":\"hi\",\"model\":\"deepseek\"}\n\n".getBytes(StandardCharsets.UTF_8));
            return null;
        }).when(pythonAiClient).copyChatStream(any(), any(), nullable(String.class));

        MvcResult result = mvc.perform(post("/api/chat/stream")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"message\":\"你好\"}"))
                .andExpect(request().asyncStarted())
                .andReturn();

        mvc.perform(asyncDispatch(result))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(MediaType.TEXT_EVENT_STREAM))
                .andExpect(content().string(org.hamcrest.Matchers.containsString("event: done")));
    }
}
