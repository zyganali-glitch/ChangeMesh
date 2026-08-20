FROM python:3.13-slim

WORKDIR /app

# Copy dependency definition and source
COPY pyproject.toml .
COPY README.md .
COPY domain ./domain
COPY events ./events
COPY integrations ./integrations
COPY src ./src
COPY service_app.py .

RUN pip install --no-cache-dir .

ENV PORT=8080
ENV GOOGLE_CLOUD_PROJECT=project-af5e1c99-3bc4-424f-b53
ENV GOOGLE_CLOUD_LOCATION=europe-west3

EXPOSE 8080

CMD ["python", "service_app.py"]
