#!/usr/bin/env bash
# RegOps Copilot 本地开发编排：db(pgvector 容器) + python-ai + java-service + web
#
#   ./scripts/dev.sh up                 启动全部
#   ./scripts/dev.sh up db python       只启动指定服务
#   ./scripts/dev.sh status             端口 / PID / 健康检查
#   ./scripts/dev.sh logs java          跟踪日志
#   ./scripts/dev.sh stop               停掉全部（db 数据保留在 volume 里）
#   ./scripts/dev.sh restart
#
# 环境变量：
#   MVN_OFFLINE=0   走联网 Maven（默认 1，离线，用本地 ~/.m2 依赖）
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="$ROOT/.dev-logs"

DB_CONTAINER="regops-db"
PY_PORT=8000
JAVA_PORT=8080
WEB_PORT=5173

MVN_OFFLINE="${MVN_OFFLINE:-1}"

ALL_SERVICES="db python java web"

# 非 TTY（重定向 / CI）时不输出颜色转义，避免日志里出现乱码
if [ -t 1 ]; then
  C_CYAN=$'\033[36m'; C_GREEN=$'\033[32m'; C_YELLOW=$'\033[33m'; C_RED=$'\033[31m'; C_OFF=$'\033[0m'
else
  C_CYAN=''; C_GREEN=''; C_YELLOW=''; C_RED=''; C_OFF=''
fi

info() { printf '%s>%s %s\n' "$C_CYAN" "$C_OFF" "$*"; }
ok()   { printf '%sOK%s   %s\n' "$C_GREEN" "$C_OFF" "$*"; }
warn() { printf '%sWARN%s %s\n' "$C_YELLOW" "$C_OFF" "$*"; }
die()  { printf '%sFAIL%s %s\n' "$C_RED" "$C_OFF" "$*" >&2; exit 1; }

# 端口空闲时 lsof 退出码为 1，配合 pipefail 会误伤 set -e，故显式吞掉
port_pid() { lsof -nP -iTCP:"$1" -sTCP:LISTEN -t 2>/dev/null | head -1 || true; }

pid_of() {
  local pidf="$LOG_DIR/$1.pid"
  [ -f "$pidf" ] || return 1
  local pid
  pid="$(cat "$pidf")"
  kill -0 "$pid" 2>/dev/null || return 1
  echo "$pid"
}

http_ok() { curl -fsS -m 3 -o /dev/null "$1" 2>/dev/null; }

# macOS 没有 setsid，用 python 代劳：setsid() 后原地 execvp，
# 进程号不变（pid 文件仍然准确），但已脱离父 shell 的会话与进程组，
# 关掉终端或父 shell 被整组清理时服务不会跟着死。
DETACH_PY='import os, sys
try:
    os.setsid()
except OSError:
    pass
os.execvp(sys.argv[1], sys.argv[1:])'

if [ -x "$ROOT/python-ai/.venv/bin/python" ]; then
  PYTHON_BIN="$ROOT/python-ai/.venv/bin/python"
else
  PYTHON_BIN="$(command -v python3 || true)"
fi

# 后台拉起一个服务：start_bg <name> <workdir> <cmd...>
start_bg() {
  local name="$1" dir="$2"
  shift 2
  mkdir -p "$LOG_DIR"
  if [ -n "$PYTHON_BIN" ]; then
    ( cd "$dir" && exec "$PYTHON_BIN" -c "$DETACH_PY" "$@" >"$LOG_DIR/$name.log" 2>&1 </dev/null ) &
  else
    warn "未找到 python3，服务将不脱离会话（关闭终端会一并退出）"
    ( cd "$dir" && exec nohup "$@" >"$LOG_DIR/$name.log" 2>&1 </dev/null ) &
  fi
  local pid=$!
  echo "$pid" >"$LOG_DIR/$name.pid"
  disown "$pid" 2>/dev/null || true
}

# 轮询健康检查；进程中途挂掉就立刻打印日志尾部，避免干等到超时。
wait_service() {
  local name="$1" url="$2" timeout="${3:-60}" pid i
  pid="$(cat "$LOG_DIR/$name.pid" 2>/dev/null || echo '')"
  for ((i = 0; i < timeout * 2; i++)); do
    if http_ok "$url"; then return 0; fi
    if [ -n "$pid" ] && ! kill -0 "$pid" 2>/dev/null; then
      warn "$name 进程已退出，日志尾部："
      tail -n 25 "$LOG_DIR/$name.log" >&2 || true
      return 1
    fi
    sleep 0.5
  done
  warn "$name 健康检查超时（${timeout}s），日志尾部："
  tail -n 25 "$LOG_DIR/$name.log" >&2 || true
  return 1
}

ensure_docker() {
  docker info >/dev/null 2>&1 && return 0
  info "Docker 未运行，拉起 Docker Desktop…"
  open -a Docker 2>/dev/null || die "无法启动 Docker Desktop，请手动打开"
  local i
  for ((i = 0; i < 60; i++)); do
    docker info >/dev/null 2>&1 && { ok "Docker 就绪"; return 0; }
    sleep 2
  done
  die "Docker 启动超时"
}

start_db() {
  ensure_docker
  ( cd "$ROOT" && docker compose up -d db >/dev/null )
  local i state
  for ((i = 0; i < 60; i++)); do
    state="$(docker inspect --format '{{.State.Health.Status}}' "$DB_CONTAINER" 2>/dev/null || echo '')"
    [ "$state" = "healthy" ] && { ok "db 就绪 (:5432)"; return 0; }
    sleep 2
  done
  die "db 健康检查超时，排查：docker logs $DB_CONTAINER"
}

start_python() {
  local busy
  busy="$(port_pid "$PY_PORT")"
  [ -n "$busy" ] && { warn "python-ai 跳过：:$PY_PORT 已被 PID $busy 占用"; return 0; }

  local uvicorn="$ROOT/python-ai/.venv/bin/uvicorn"
  [ -x "$uvicorn" ] || die "缺少虚拟环境 python-ai/.venv，先执行：cd python-ai && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"

  start_bg python "$ROOT/python-ai" "$uvicorn" app.main:app --host 0.0.0.0 --port "$PY_PORT" --reload
  wait_service python "http://localhost:$PY_PORT/health" 90 || die "python-ai 启动失败"
  ok "python-ai 就绪 (:$PY_PORT)"
}

start_java() {
  local busy
  busy="$(port_pid "$JAVA_PORT")"
  [ -n "$busy" ] && { warn "java-service 跳过：:$JAVA_PORT 已被 PID $busy 占用"; return 0; }

  # ./mvnw 会去中央仓库下载 Maven 发行包，网络受限时必失败；优先用系统已装的 mvn。
  local -a cmd
  if command -v mvn >/dev/null 2>&1; then
    if [ "$MVN_OFFLINE" = "1" ]; then
      cmd=(mvn -o spring-boot:run)
    else
      cmd=(mvn spring-boot:run)
    fi
  else
    warn "未找到系统 mvn，回退 ./mvnw（需联网下载 Maven 发行包）"
    cmd=(./mvnw spring-boot:run)
  fi

  start_bg java "$ROOT/java-service" "${cmd[@]}"
  wait_service java "http://localhost:$JAVA_PORT/actuator/health" 240 || die "java-service 启动失败"
  ok "java-service 就绪 (:$JAVA_PORT)"
}

start_web() {
  local busy
  busy="$(port_pid "$WEB_PORT")"
  [ -n "$busy" ] && { warn "web 跳过：:$WEB_PORT 已被 PID $busy 占用"; return 0; }

  local vite="$ROOT/web/node_modules/.bin/vite"
  [ -x "$vite" ] || die "缺少前端依赖，先执行：cd web && npm install"

  # 直接跑 vite 而非 npm run dev：少一层 npm 父进程，stop 时能干净退出。
  start_bg web "$ROOT/web" "$vite"
  wait_service web "http://localhost:$WEB_PORT/" 60 || die "web 启动失败"
  ok "web 就绪 (:$WEB_PORT)"
}

stop_proc() {
  local name="$1" port="$2" pid
  if pid="$(pid_of "$name")"; then
    pkill -TERM -P "$pid" 2>/dev/null || true
    kill -TERM "$pid" 2>/dev/null || true
    local i
    for ((i = 0; i < 20; i++)); do
      kill -0 "$pid" 2>/dev/null || break
      sleep 0.5
    done
    kill -KILL "$pid" 2>/dev/null || true
    ok "$name 已停止 (PID $pid)"
  fi
  rm -f "$LOG_DIR/$name.pid"

  # reload / fork 出来的子进程可能仍占着端口，兜底清一次。
  local leftover
  leftover="$(port_pid "$port")"
  if [ -n "$leftover" ]; then
    kill -TERM $leftover 2>/dev/null || true
    sleep 1
    leftover="$(port_pid "$port")"
    [ -n "$leftover" ] && kill -KILL $leftover 2>/dev/null || true
    warn "$name 残留监听 :$port 已清理"
  fi
}

stop_db() {
  docker info >/dev/null 2>&1 || return 0
  ( cd "$ROOT" && docker compose stop db >/dev/null 2>&1 ) || true
  ok "db 已停止（数据保留在 volume db_data）"
}

cmd_up() {
  local services="${*:-$ALL_SERVICES}" svc
  for svc in $services; do
    case "$svc" in
      db)     start_db ;;
      python) start_python ;;
      java)   start_java ;;
      web)    start_web ;;
      *)      die "未知服务：$svc（可选：$ALL_SERVICES）" ;;
    esac
  done
  echo
  info "访问地址"
  echo "  前端        http://localhost:$WEB_PORT"
  echo "  Java BFF    http://localhost:$JAVA_PORT/api/health"
  echo "  python-ai   http://localhost:$PY_PORT/docs"
  echo "  Postgres    localhost:5432  (regops/regops123, db=regops_db)"
  echo
  info "日志目录 .dev-logs/ ｜ 跟踪日志 ./scripts/dev.sh logs {python|java|web}"
}

cmd_stop() {
  local services="${*:-$ALL_SERVICES}" svc
  for svc in $services; do
    case "$svc" in
      db)     stop_db ;;
      python) stop_proc python "$PY_PORT" ;;
      java)   stop_proc java "$JAVA_PORT" ;;
      web)    stop_proc web "$WEB_PORT" ;;
      *)      die "未知服务：$svc（可选：$ALL_SERVICES）" ;;
    esac
  done
}

row() { printf '  %-12s %-7s %-9s %s\n' "$1" "$2" "$3" "$4"; }

cmd_status() {
  # 表头用 ASCII：printf 按字节补齐，中文列名会把对齐撑歪
  row SERVICE PORT PID HEALTH
  local state pid
  state="$(docker inspect --format '{{.State.Status}}/{{.State.Health.Status}}' "$DB_CONTAINER" 2>/dev/null || echo '-')"
  row db 5432 "$DB_CONTAINER" "$state"

  pid="$(port_pid "$PY_PORT")"
  row python-ai "$PY_PORT" "${pid:--}" "$(http_ok "http://localhost:$PY_PORT/health" && echo ok || echo down)"

  pid="$(port_pid "$JAVA_PORT")"
  row java "$JAVA_PORT" "${pid:--}" "$(http_ok "http://localhost:$JAVA_PORT/actuator/health" && echo ok || echo down)"

  pid="$(port_pid "$WEB_PORT")"
  row web "$WEB_PORT" "${pid:--}" "$(http_ok "http://localhost:$WEB_PORT/" && echo ok || echo down)"

  echo
  # 端到端链路：浏览器 → vite 代理 → java → python-ai
  # Java 的 /api/health 即使下游挂了也返回 200，必须看响应体里的 pythonAi 状态
  local chain
  chain="$(curl -fsS -m 5 "http://localhost:$WEB_PORT/api/health" 2>/dev/null || echo '')"
  case "$chain" in
    *'"pythonAi"'*'"ok"'*) ok "全链路连通 web -> java -> python-ai" ;;
    '')                    warn "全链路未连通：web 或 java 未响应" ;;
    *)                     warn "java 可达但 python-ai 异常：$chain" ;;
  esac
}

cmd_logs() {
  local name="${1:-}"
  case "$name" in
    python|java|web) tail -f "$LOG_DIR/$name.log" ;;
    db)              docker logs -f "$DB_CONTAINER" ;;
    *)               die "用法：./scripts/dev.sh logs {python|java|web|db}" ;;
  esac
}

case "${1:-up}" in
  up)      shift || true; cmd_up "$@" ;;
  stop)    shift || true; cmd_stop "$@" ;;
  restart) shift || true; cmd_stop "$@"; echo; cmd_up "$@" ;;
  status)  cmd_status ;;
  logs)    shift || true; cmd_logs "$@" ;;
  *)       die "用法：./scripts/dev.sh {up|stop|restart|status|logs} [db python java web]" ;;
esac
