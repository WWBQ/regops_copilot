regops-copilot/
├── java-service/                         # Java 后端服务 (Spring Boot 3, JDK21)
│   ├── src/main/java/com/regops/java_service/
│   │   ├── controller/                   # 控制器层（REST API）
│   │   ├── service/                      # 业务逻辑层
│   │   ├── repository/                   # 数据访问层（JPA）
│   │   ├── entity/                       # 数据库实体类
│   │   ├── dto/                          # 数据传输对象
│   │   ├── config/                       # 配置类（CORS、拦截器等）
│   │   ├── exception/                    # 全局异常处理
│   │   ├── util/                         # 工具类
│   │   └── JavaServiceApplication.java   # Spring Boot 启动类
│   ├── src/main/resources/
│   │   ├── application.yml               # Spring Boot 配置文件
│   │   ├── schema.sql                    # 数据库结构初始化
│   │   └── data.sql                      # 数据库初始数据
│   ├── pom.xml                           # Maven 配置
│   └── Dockerfile                        # Java 服务 Dockerfile
│
├── python-ai/                            # Python AI 服务 (FastAPI + RAG + Agent)
│   ├── app/
│   │   ├── api/                          # FastAPI 路由
│   │   ├── ingest/                       # 文档解析、三表提取、勾稽校验
│   │   ├── rag/                          # 检索、RRF、Rerank、引用、拒答
│   │   ├── text2sql/                     # Schema 检索、SQL 生成、EXPLAIN 校验
│   │   ├── agents/                       # LangGraph 状态图、数字校验节点
│   │   ├── prompts/                      # Prompt 模板库（含版本与变更记录）
│   │   ├── models/                       # 模型封装（LLM、Embedding、Reranker）
│   │   ├── services/                     # AI 服务逻辑
│   │   └── main.py                       # FastAPI 入口
│   ├── requirements.txt                  # Python 依赖
│   └── Dockerfile                        # Python 服务 Dockerfile
│
├── eval/                                  # 评测资产（可复跑、版本固定）
│   ├── golden/                           # 黄金集：RAG 80–100 · 问数 30 · Agent 20 · 安全 25
│   ├── reports/                          # 消融与回归报告（按日期与版本归档）
│   ├── prompt_ab/                        # Prompt A/B 实验脚本与结果
│   └── badcases/                         # 坏例库与层级归因
│
├── web/                                   # 前端 (Vue3 + Vite)
│   ├── src/
│   │   ├── assets/                       # 静态资源
│   │   ├── components/                   # 公共组件
│   │   ├── views/                        # 页面视图
│   │   ├── router/                       # 路由配置
│   │   ├── store/                        # 状态管理（Pinia/Vuex）
│   │   ├── api/                          # 前端 API 封装
│   │   ├── utils/                        # 工具函数
│   │   ├── App.vue                       # 根组件
│   │   └── main.js                       # 前端入口
│   ├── index.html                        # 页面入口
│   ├── package.json                      # 前端依赖
│   ├── vite.config.js                    # Vite 配置
│   └── Dockerfile                        # Vue 前端 Dockerfile
│
├── docs/                                  # 文档目录
│   ├── architecture.md                   # 系统架构设计
│   ├── api-spec.md                       # API 规范（Java + Python）
│   ├── ai-design.md                      # AI 设计（RAG、问数、Agent）
│   ├── DATA_SOURCES.md                   # 公开数据源清单与使用边界声明
│   ├── security.md                       # 安全边界：SQL 只读、PII、注入红队
│   ├── dify-comparison.md                # Dify 对照实现与选型判断
│   └── deployment.md                     # 部署文档（Compose、K8s、信创适配）
│
├── k8s/                                   # 最小 K8s 清单（kind / minikube 可跑）
├── compose.yaml                           # Docker Compose 编排文件
├── .env.example                           # 环境变量示例
└── README.md                              # 项目说明文档