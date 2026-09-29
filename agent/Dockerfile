FROM python:3.12-slim

WORKDIR /app

# 固定 a2a-sdk 0.3.22（最新版 1.x 结构已变，a2a.server.apps 被移除）。
# malt_engine 只用标准库 re，不依赖 networkx / solid_step（那些由评测器在 exec namespace 里预置）。
# 用清华源加速（服务器到 pypi.org 仅 30 kB/s），uvicorn 用基础版（无需 standard 的 uvloop/watchfiles）。
RUN pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple "a2a-sdk[http-server]==0.3.22" uvicorn

COPY malt_engine.py malt_purple_agent.py ./

EXPOSE 8080

CMD ["python", "malt_purple_agent.py", "--host", "0.0.0.0", "--port", "8080"]
