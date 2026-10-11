FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_HOME=/app/data/hf \
    PYTHONPATH=/app/python-ai

WORKDIR /app

RUN set -eux; \
    for f in /etc/apt/sources.list /etc/apt/sources.list.d/debian.sources; do \
      [ -f "$f" ] || continue; \
      sed -i 's|deb.debian.org|mirrors.aliyun.com|g; s|security.debian.org|mirrors.aliyun.com|g' "$f"; \
    done; \
    apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        curl \
        libgl1 \
        libglib2.0-0 \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY python-ai/requirements.txt python-ai/requirements.txt
# torchvision 必须跟 torch 2.6.0+cu124 成对。requirements 先装进来的 torchvision 是按另一版 torch 编译的，
# 之后如果只重装 torch，运行时会报 torchvision::nms does not exist。
RUN pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple -r python-ai/requirements.txt \
    && pip install --no-cache-dir --force-reinstall 'torch==2.6.0+cu124' --index-url https://download.pytorch.org/whl/cu124 \
    && pip install --no-cache-dir --force-reinstall --no-deps 'torchvision==0.21.0+cu124' --index-url https://download.pytorch.org/whl/cu124

COPY python-ai python-ai
COPY eval eval

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--app-dir", "python-ai"]
