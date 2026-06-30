FROM python:3.12-slim
WORKDIR /app
COPY . .
RUN pip install -e . --no-cache-dir
CMD ["python", "-m", "core.agent_graph"]
