FROM python:3.11-slim

WORKDIR /app

COPY enrichment_service/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY shared_utils/requirements.txt ./shared_utils_requirements.txt
RUN pip install --no-cache-dir -r ./shared_utils_requirements.txt

COPY enrichment_service/ ./enrichment_service/
COPY shared_utils/ ./shared_utils/

CMD ["python", "enrichment_service/main.py"]