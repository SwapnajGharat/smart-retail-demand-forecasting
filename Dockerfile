# syntax=docker/dockerfile:1

FROM python:3.12-slim AS python-dependencies
WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.12-slim AS backend
WORKDIR /app
COPY --from=python-dependencies /install /usr/local
COPY main.py model.json ./
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

FROM nginx:1.27-alpine AS frontend
COPY frontend/ /usr/share/nginx/html/
COPY sales_data.csv /usr/share/nginx/html/sales_data.csv
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
