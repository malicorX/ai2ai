FROM python:3.11-slim

WORKDIR /app
COPY ../agent_template/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY ../agent_template/agent.py ./agent.py

ENV PYTHONUNBUFFERED=1
ENV AGENT_ID=agent_1
ENV DISPLAY_NAME=Agent 1
CMD ["python", "agent.py"]

