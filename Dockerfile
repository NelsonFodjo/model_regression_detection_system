FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY classifier.py compare_runs.py email_sender.py main.py run_eval.py whatsapp.py ./
COPY prompts ./prompts

CMD ["python", "main.py"]