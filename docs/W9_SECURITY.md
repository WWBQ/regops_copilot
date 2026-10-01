# W9-2 安全边界

本项目的安全约束在服务端执行，不靠提示词独立保障：

- 问数只查询 `fin_metric` 中通过质量门的事实；缺失、冲突或待复核数据不作为可回答数字。
- RAG 检索按可信部门过滤公司范围，引用回到具体文档；终稿数字还要经过证据校验，无依据则拦截。
- Java 文档入口实施部门权限，用户 JWT 不转发给 Python。
- 日志与 Trace 对手机号、身份证号、账号和密钥脱敏。

对应自动化验证包括 `test_asknum.py`、`test_evidence.py`、`test_rag_guard.py`、`DeptAclTest`，以及 RAG/问数黄金集。
