#FROM cgr.dev/chainguard/python:latest-dev as builder
#
#WORKDIR /app
#COPY requirements.txt ./
#RUN pip install -r requirements.txt --user
#
#FROM cgr.dev/chainguard/python:latest
#
#WORKDIR /app
#
#COPY --from=builder /home/nonroot/.local/lib/python3.11/site-packages /home/nonroot/.local/lib/python3.11/site-packages
#COPY --from=builder /home/nonroot/.local/bin /home/nonroot/.local/bin
#COPY --from=builder /app /app
#
#COPY LICENSE ./
#COPY *.py ./
#COPY *.yaml ./
#
#USER nonroot
#CMD ["/home/nonroot/.local/bin/kopf", "run", "-n", "ort", "/app/ort_operator.py"]

FROM python:3.11

WORKDIR /app
COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY LICENSE ./
COPY *.py ./
COPY *.yaml ./

CMD ["kopf", "run", "-n", "ort", "/app/ort_operator.py"]

