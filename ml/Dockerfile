FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY anomaly_detector.py .

EXPOSE 8001
CMD ["python", "anomaly_detector.py"]
