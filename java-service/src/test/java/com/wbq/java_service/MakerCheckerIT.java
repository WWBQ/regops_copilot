package com.wbq.java_service;

import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.Connection;
import java.sql.DriverManager;
import java.util.UUID;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;

import com.wbq.java_service.client.PythonAiClient;
import com.wbq.java_service.review.ReviewTxGuard;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.core.io.FileSystemResource;
import org.springframework.http.MediaType;
import org.springframework.jdbc.datasource.init.ScriptUtils;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.postgresql.PostgreSQLContainer;

import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.doNothing;
import static org.mockito.Mockito.doThrow;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
@Testcontainers(disabledWithoutDocker = true)
class MakerCheckerIT {

    @Container
    static final PostgreSQLContainer postgres = new PostgreSQLContainer("postgres:16-alpine")
            .withDatabaseName("regops_db")
            .withUsername("regops")
            .withPassword("regops123");

    @DynamicPropertySource
    static void datasource(DynamicPropertyRegistry registry) {
        applySchema();
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
        registry.add("spring.datasource.driver-class-name", () -> "org.postgresql.Driver");
        registry.add("regops.auth.seed", () -> "true");
    }

    @Autowired
    MockMvc mvc;

    @Autowired
    ObjectMapper objectMapper;

    @MockitoBean
    PythonAiClient pythonAiClient;

    @MockitoBean
    ReviewTxGuard txGuard;

    @BeforeEach
    void resetGuard() {
        doNothing().when(txGuard).afterWrite();
    }

    @Test
    void loginValidationAndDuplicateCreate() throws Exception {
        mvc.perform(post("/api/reviews/tickets")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"company_code\":\"002594\",\"title\":\"x\",\"reason\":\"y\"}"))
                .andExpect(status().isUnauthorized());
        mvc.perform(post("/api/auth/login")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"username\":\"analyst\",\"password\":\"wrong\"}"))
                .andExpect(status().isUnauthorized());
        String token = login("analyst", "analyst123");
        mvc.perform(post("/api/reviews/tickets")
                        .header("Authorization", bearer(token))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"company_code\":\"002594\",\"reason\":\"缺标题\"}"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.extra.error_code").value("invalid_params"));
        String key = "idem-" + UUID.randomUUID();
        String body = ticketJson("关联交易复核");
        JsonNode first = json(mvc.perform(post("/api/reviews/tickets")
                        .header("Authorization", bearer(token))
                        .header("Idempotency-Key", key)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(body))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("PENDING"))
                .andExpect(jsonPath("$.replayed").value(false))
                .andReturn());
        JsonNode second = json(mvc.perform(post("/api/reviews/tickets")
                        .header("Authorization", bearer(token))
                        .header("Idempotency-Key", key)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(body))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.replayed").value(true))
                .andReturn());
        assertThat(second.get("id").asText()).isEqualTo(first.get("id").asText());
    }

    @Test
    void rmCannotSeeInternalResearchOrReview() throws Exception {
        String rm = login("rm", "rm123");
        MvcResult customers = mvc.perform(get("/api/customers").header("Authorization", bearer(rm)))
                .andExpect(status().isOk())
                .andReturn();
        String payload = customers.getResponse().getContentAsString();
        assertThat(payload).doesNotContain("INTERNAL_RESEARCH");
        assertThat(payload).contains("CLIENT");
        mvc.perform(get("/api/reviews/tickets").header("Authorization", bearer(rm)))
                .andExpect(status().isForbidden());
        mvc.perform(post("/api/tools/lookup")
                        .header("Authorization", bearer(rm))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"company_code\":\"002594\",\"concept\":\"revenue\",\"year\":2024}"))
                .andExpect(status().isForbidden());
        mvc.perform(get("/api/documents/002594_2024/viewer-url").header("Authorization", bearer(rm)))
                .andExpect(status().isNotFound());
    }

    @Test
    void selfReviewRejectedAndHappyPath() throws Exception {
        String checker = login("checker", "checker123");
        String id = json(mvc.perform(post("/api/reviews/tickets")
                        .header("Authorization", bearer(checker))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(ticketJson("自审探针")))
                .andExpect(status().isOk())
                .andReturn()).get("id").asText();
        mvc.perform(post("/api/reviews/tickets/" + id + "/submit").header("Authorization", bearer(checker)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("SUBMITTED"));
        mvc.perform(post("/api/reviews/tickets/" + id + "/approve")
                        .header("Authorization", bearer(checker))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"reason\":\"自己批自己\"}"))
                .andExpect(status().isForbidden())
                .andExpect(jsonPath("$.extra.error_code").value("self_review"));

        String analyst = login("analyst", "analyst123");
        String ticketId = json(mvc.perform(post("/api/reviews/tickets")
                        .header("Authorization", bearer(analyst))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(ticketJson("双人复核主路径")))
                .andExpect(status().isOk())
                .andReturn()).get("id").asText();
        mvc.perform(post("/api/reviews/tickets/" + ticketId + "/submit").header("Authorization", bearer(analyst)))
                .andExpect(status().isOk());
        mvc.perform(post("/api/reviews/tickets/" + ticketId + "/approve")
                        .header("Authorization", bearer(checker))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"reason\":\"条款引用齐全\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("REVIEWED"))
                .andExpect(jsonPath("$.reviewedBy").value("checker"));
        mvc.perform(post("/api/reviews/tickets/" + ticketId + "/submit").header("Authorization", bearer(analyst)))
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.extra.error_code").value("invalid_state"));
        mvc.perform(get("/api/audit/events")
                        .header("Authorization", bearer(checker))
                        .param("entityType", "review_ticket")
                        .param("entityId", ticketId))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[0].actorUsername").exists());
    }

    @Test
    void concurrentReviewOnlyOneSucceeds() throws Exception {
        String analyst = login("analyst", "analyst123");
        String checker = login("checker", "checker123");
        String admin = login("admin", "admin123");
        String id = json(mvc.perform(post("/api/reviews/tickets")
                        .header("Authorization", bearer(analyst))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(ticketJson("并发复核")))
                .andExpect(status().isOk())
                .andReturn()).get("id").asText();
        mvc.perform(post("/api/reviews/tickets/" + id + "/submit").header("Authorization", bearer(analyst)))
                .andExpect(status().isOk());
        CountDownLatch start = new CountDownLatch(1);
        AtomicInteger ok = new AtomicInteger();
        AtomicInteger conflict = new AtomicInteger();
        Runnable approveChecker = () -> decide(checker, id, start, ok, conflict);
        Runnable approveAdmin = () -> decide(admin, id, start, ok, conflict);
        Thread t1 = new Thread(approveChecker);
        Thread t2 = new Thread(approveAdmin);
        t1.start();
        t2.start();
        start.countDown();
        t1.join();
        t2.join();
        assertThat(ok.get()).isEqualTo(1);
        assertThat(conflict.get()).isEqualTo(1);
        mvc.perform(get("/api/reviews/tickets/" + id).header("Authorization", bearer(checker)))
                .andExpect(jsonPath("$.status").value("REVIEWED"));
    }

    @Test
    void injectedFailureRollsBackStatusAndAudit() throws Exception {
        String analyst = login("analyst", "analyst123");
        String checker = login("checker", "checker123");
        String id = json(mvc.perform(post("/api/reviews/tickets")
                        .header("Authorization", bearer(analyst))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(ticketJson("回滚探针")))
                .andExpect(status().isOk())
                .andReturn()).get("id").asText();
        mvc.perform(post("/api/reviews/tickets/" + id + "/submit").header("Authorization", bearer(analyst)))
                .andExpect(status().isOk());
        doThrow(new IllegalStateException("injected")).when(txGuard).afterWrite();
        mvc.perform(post("/api/reviews/tickets/" + id + "/approve")
                        .header("Authorization", bearer(checker))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"reason\":\"应回滚\"}"))
                .andExpect(status().isInternalServerError());
        doNothing().when(txGuard).afterWrite();
        mvc.perform(get("/api/reviews/tickets/" + id).header("Authorization", bearer(checker)))
                .andExpect(jsonPath("$.status").value("SUBMITTED"))
                .andExpect(jsonPath("$.reviewedBy").doesNotExist());
        String audit = mvc.perform(get("/api/audit/events")
                        .header("Authorization", bearer(checker))
                        .param("entityType", "review_ticket")
                        .param("entityId", id))
                .andExpect(status().isOk())
                .andReturn()
                .getResponse()
                .getContentAsString();
        assertThat(audit).doesNotContain("APPROVE_TICKET");
    }

    private void decide(String token, String id, CountDownLatch start, AtomicInteger ok, AtomicInteger conflict) {
        try {
            start.await();
            int status = mvc.perform(post("/api/reviews/tickets/" + id + "/approve")
                            .header("Authorization", bearer(token))
                            .contentType(MediaType.APPLICATION_JSON)
                            .content("{\"reason\":\"并发\"}"))
                    .andReturn()
                    .getResponse()
                    .getStatus();
            if (status == 200) {
                ok.incrementAndGet();
            } else if (status == 409) {
                conflict.incrementAndGet();
            }
        } catch (Exception ex) {
            throw new IllegalStateException(ex);
        }
    }

    private String login(String username, String password) throws Exception {
        JsonNode body = json(mvc.perform(post("/api/auth/login")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"username\":\"" + username + "\",\"password\":\"" + password + "\"}"))
                .andExpect(status().isOk())
                .andReturn());
        return body.get("token").asText();
    }

    private JsonNode json(MvcResult result) throws Exception {
        return objectMapper.readTree(result.getResponse().getContentAsString());
    }

    private static String bearer(String token) {
        return "Bearer " + token;
    }

    private static String ticketJson(String title) {
        return "{\"company_code\":\"002594\",\"title\":\"" + title + "\",\"reason\":\"需复核\",\"conclusion\":\"并列查数\"}";
    }

    private static void applySchema() {
        Path dir = sqlDir();
        try (Connection connection = DriverManager.getConnection(
                postgres.getJdbcUrl(), postgres.getUsername(), postgres.getPassword()
        )) {
            ScriptUtils.executeSqlScript(connection, new FileSystemResource(dir.resolve("w6_review_draft.sql")));
            ScriptUtils.executeSqlScript(connection, new FileSystemResource(dir.resolve("w7_identity.sql")));
        } catch (Exception ex) {
            throw new IllegalStateException("failed to apply W7 SQL from " + dir, ex);
        }
    }

    private static Path sqlDir() {
        Path cwd = Path.of("").toAbsolutePath();
        Path[] candidates = {cwd.resolve("docs/sql"), cwd.resolve("../docs/sql")};
        for (Path candidate : candidates) {
            if (Files.isRegularFile(candidate.resolve("w7_identity.sql"))) {
                return candidate.normalize();
            }
        }
        throw new IllegalStateException("docs/sql not found from " + cwd);
    }
}
