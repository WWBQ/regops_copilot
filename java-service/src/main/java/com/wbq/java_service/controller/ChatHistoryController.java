package com.wbq.java_service.controller;

import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.UUID;

import com.wbq.java_service.auth.AuthSupport;
import com.wbq.java_service.exception.BusinessException;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

import tools.jackson.databind.ObjectMapper;

/** 登录用户的合规问答历史；所有查询由 JWT 身份限定，不接受客户端 user_id。 */
@RestController
@RequestMapping("/api/chat-history")
public class ChatHistoryController {

    private final JdbcTemplate jdbc;
    private final ObjectMapper mapper;

    public ChatHistoryController(JdbcTemplate jdbc, ObjectMapper mapper) {
        this.jdbc = jdbc;
        this.mapper = mapper;
    }

    public record Entry(UUID sessionId, String title, boolean customTitle, Instant updatedAt) {}
    public record Detail(UUID sessionId, String title, boolean customTitle, Instant updatedAt, Object messages) {}
    public record Snapshot(UUID sessionId, String title, boolean customTitle,
                           Instant updatedAt, List<Map<String, Object>> messages) {}

    @GetMapping
    public List<Entry> list() {
        UUID userId = userId();
        return jdbc.query("""
                SELECT session_id, title, custom_title, updated_at
                FROM chat_history WHERE user_id = ? ORDER BY updated_at DESC
                """, (rs, row) -> new Entry(
                rs.getObject("session_id", UUID.class), rs.getString("title"),
                rs.getBoolean("custom_title"), rs.getTimestamp("updated_at").toInstant()), userId);
    }

    @GetMapping("/{sessionId}")
    public Detail get(@PathVariable UUID sessionId) {
        List<Detail> rows = jdbc.query("""
                SELECT session_id, title, custom_title, updated_at, messages_json
                FROM chat_history WHERE user_id = ? AND session_id = ?
                """, (rs, row) -> new Detail(
                rs.getObject("session_id", UUID.class), rs.getString("title"),
                rs.getBoolean("custom_title"), rs.getTimestamp("updated_at").toInstant(),
                mapper.readValue(rs.getString("messages_json"), Object.class)), userId(), sessionId);
        if (rows.isEmpty()) throw BusinessException.notFound("对话不存在");
        return rows.getFirst();
    }

    @PutMapping("/{sessionId}")
    public Entry save(@PathVariable UUID sessionId, @RequestBody Snapshot snapshot) {
        if (snapshot.sessionId() != null && !sessionId.equals(snapshot.sessionId())) {
            throw BusinessException.badRequest("会话 ID 不一致");
        }
        String json = checkedMessages(snapshot.messages());
        String title = checkedTitle(snapshot.title());
        UUID userId = userId();
        jdbc.update("""
                INSERT INTO chat_history (user_id, session_id, title, custom_title, messages_json)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT (user_id, session_id) DO UPDATE SET
                  title = EXCLUDED.title, custom_title = EXCLUDED.custom_title,
                  messages_json = EXCLUDED.messages_json, updated_at = NOW()
                """, userId, sessionId, title, snapshot.customTitle(), json);
        return jdbc.queryForObject("""
                SELECT session_id, title, custom_title, updated_at
                FROM chat_history WHERE user_id = ? AND session_id = ?
                """, (rs, row) -> new Entry(
                rs.getObject("session_id", UUID.class), rs.getString("title"),
                rs.getBoolean("custom_title"), rs.getTimestamp("updated_at").toInstant()), userId, sessionId);
    }

    /** 旧 localStorage 只导入数据库不存在的会话，不覆盖其他设备上的新消息。 */
    @PostMapping("/import")
    public List<Entry> importLocal(@RequestBody List<Snapshot> snapshots) {
        if (snapshots == null || snapshots.size() > 30) {
            throw BusinessException.badRequest("最多导入 30 个会话");
        }
        UUID userId = userId();
        for (Snapshot snapshot : snapshots) {
            if (snapshot.sessionId() == null) continue;
            String json = checkedMessages(snapshot.messages());
            String title = checkedTitle(snapshot.title());
            Instant at = snapshot.updatedAt() == null ? Instant.now() : snapshot.updatedAt();
            jdbc.update("""
                    INSERT INTO chat_history
                      (user_id, session_id, title, custom_title, messages_json, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT (user_id, session_id) DO NOTHING
                    """, userId, snapshot.sessionId(), title, snapshot.customTitle(), json,
                    java.sql.Timestamp.from(at));
        }
        return list();
    }

    @DeleteMapping("/{sessionId}")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void delete(@PathVariable UUID sessionId) {
        int deleted = jdbc.update("DELETE FROM chat_history WHERE user_id = ? AND session_id = ?", userId(), sessionId);
        if (deleted == 0) throw BusinessException.notFound("对话不存在");
    }

    @PatchMapping("/{sessionId}/title")
    public Entry rename(@PathVariable UUID sessionId, @RequestBody Map<String, String> body) {
        String title = checkedTitle(body.get("title"));
        UUID userId = userId();
        int updated = jdbc.update("""
                UPDATE chat_history SET title = ?, custom_title = TRUE, updated_at = NOW()
                WHERE user_id = ? AND session_id = ?
                """, title, userId, sessionId);
        if (updated == 0) throw BusinessException.notFound("对话不存在");
        return jdbc.queryForObject("""
                SELECT session_id, title, custom_title, updated_at
                FROM chat_history WHERE user_id = ? AND session_id = ?
                """, (rs, row) -> new Entry(
                rs.getObject("session_id", UUID.class), rs.getString("title"),
                rs.getBoolean("custom_title"), rs.getTimestamp("updated_at").toInstant()), userId, sessionId);
    }

    private UUID userId() {
        return AuthSupport.requireUser().publicId();
    }

    private String checkedTitle(String title) {
        if (title == null || title.isBlank()) throw BusinessException.badRequest("对话标题不能为空");
        return title.strip().length() > 256 ? title.strip().substring(0, 256) : title.strip();
    }

    private String checkedMessages(List<Map<String, Object>> messages) {
        if (messages == null || messages.size() > 200) throw BusinessException.badRequest("消息数量超限");
        for (Map<String, Object> message : messages) {
            if (message == null || !(message.get("content") instanceof String content)
                    || content.length() > 100_000 || !List.of("user", "assistant").contains(message.get("role"))) {
                throw BusinessException.badRequest("消息格式无效");
            }
        }
        String json = mapper.writeValueAsString(messages);
        if (json.length() > 2_000_000) throw BusinessException.badRequest("会话内容过大");
        return json;
    }
}
