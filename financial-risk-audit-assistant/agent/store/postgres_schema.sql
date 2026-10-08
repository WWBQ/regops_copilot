CREATE TABLE IF NOT EXISTS threads (
  thread_id TEXT PRIMARY KEY, title TEXT NOT NULL, user_prompt TEXT,
  repo_url TEXT, repo_owner TEXT, repo_name TEXT, branch_name TEXT, pr_url TEXT,
  latest_run_status TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS runs (
  run_id TEXT PRIMARY KEY, thread_id TEXT NOT NULL, status TEXT NOT NULL,
  started_at TEXT NOT NULL, finished_at TEXT, error TEXT, user_question TEXT
);
CREATE TABLE IF NOT EXISTS run_events (
  id TEXT PRIMARY KEY, thread_id TEXT NOT NULL, kind TEXT NOT NULL, title TEXT NOT NULL,
  status TEXT NOT NULL, detail TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS agent_trace_events (
  id TEXT PRIMARY KEY, run_id TEXT NOT NULL, thread_id TEXT NOT NULL,
  phase TEXT NOT NULL, label TEXT NOT NULL, status TEXT NOT NULL,
  started_at TEXT NOT NULL, finished_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_agent_trace_run_time ON agent_trace_events(run_id, started_at);
CREATE TABLE IF NOT EXISTS thread_messages (
  message_id TEXT PRIMARY KEY, thread_id TEXT NOT NULL, run_id TEXT,
  author TEXT NOT NULL, content TEXT NOT NULL, metadata TEXT, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS thread_plans (
  plan_id TEXT PRIMARY KEY, thread_id TEXT NOT NULL, run_id TEXT,
  status TEXT NOT NULL, prompt TEXT NOT NULL, plan_text TEXT NOT NULL,
  plan_path TEXT NOT NULL, created_at TEXT NOT NULL, approved_at TEXT
);
CREATE TABLE IF NOT EXISTS review_findings (
  id TEXT PRIMARY KEY, thread_id TEXT NOT NULL, file TEXT NOT NULL, line INTEGER,
  severity TEXT NOT NULL, title TEXT NOT NULL, description TEXT NOT NULL,
  status TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS risk_audit_results (
  result_id TEXT PRIMARY KEY, run_id TEXT NOT NULL UNIQUE, thread_id TEXT NOT NULL,
  company_code TEXT NOT NULL, company_name TEXT NOT NULL, year INTEGER NOT NULL,
  status TEXT NOT NULL, summary TEXT NOT NULL, evidence_gaps TEXT NOT NULL,
  report_markdown TEXT NOT NULL, answer_hash TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_risk_results_thread_created ON risk_audit_results(thread_id, created_at);
CREATE TABLE IF NOT EXISTS risk_audit_findings (
  id TEXT PRIMARY KEY, result_id TEXT NOT NULL, thread_id TEXT NOT NULL,
  ordinal INTEGER NOT NULL, risk_type TEXT NOT NULL, severity TEXT NOT NULL,
  conclusion TEXT NOT NULL, evidence_ids TEXT NOT NULL, data_points TEXT NOT NULL,
  uncertainty TEXT NOT NULL, review_question TEXT NOT NULL, review_status TEXT NOT NULL,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_risk_findings_result_ordinal ON risk_audit_findings(result_id, ordinal);
CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at TEXT NOT NULL
);
