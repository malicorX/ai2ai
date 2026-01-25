FROM python:3.11-slim

WORKDIR /app
RUN mkdir -p /app/agent_template
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY agent.py .
COPY langgraph_runtime.py ./agent_template/langgraph_runtime.py
COPY langgraph_agent.py ./agent_template/langgraph_agent.py

ENV PYTHONUNBUFFERED=1
CMD ["python", "agent.py"]

