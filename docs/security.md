# 安全边界

金融问答场景的安全不靠系统提示「请勿越狱」。实现与 25 条红队见 [`W9_SECURITY.md`](./W9_SECURITY.md)。

- 工具白名单：没有 `execute_sql`
- 部门 ACL：越权与无答案各 20 题**在 Python 检索层**验证泄露为 0；Java BFF 部门头校验仅在已登录时生效，未登录演示路径不强制部门约束
- 数字：`evidence.py` 回溯，无证据不放行
- PII / 密钥：日志、Trace、评测文本都走 `mask_for_log`
