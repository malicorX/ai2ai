FROM python:3.11-slim

WORKDIR /app
RUN mkdir -p /app/agent_template
COPY agent_template/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY agent_template/agent.py ./agent.py
COPY agent_template/langgraph_runtime.py ./agent_template/langgraph_runtime.py

ENV PYTHONUNBUFFERED=1
ENV AGENT_ID=agent_2
ENV DISPLAY_NAME="Agent 2"
CMD ["python", "agent.py"]

