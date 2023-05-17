FROM cgr.dev/chainguard/python:3.11

RUN groupadd -g 10001 nonroot
RUN useradd -u 10001 -g 10001 -d /app nonroot

WORKDIR /app
COPY LICENSE ./
COPY requirements.txt ./
COPY *.py ./
COPY *.yaml ./
RUN pip install -r ./requirements.txt

USER nonroot
CMD ["kopf", "run", "-n", "ort", "/app/ort_operator.py"]

