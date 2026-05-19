FROM python:3.11-slim

WORKDIR /app

COPY event_engine_service/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY event_engine_service/ ./event_engine_service/
COPY shared_utils/ ./shared_utils/

CMD ["python", "event_engine_service/main.py"]