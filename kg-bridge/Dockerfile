FROM python:3.12-slim AS py-aas-rdf-wheel

WORKDIR /build

COPY py-aas-rdf ./py-aas-rdf
RUN pip wheel --no-cache-dir --wheel-dir /dist ./py-aas-rdf

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY kg-bridge/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY --from=py-aas-rdf-wheel /dist /wheels
RUN pip install --no-cache-dir /wheels/py_aas_rdf-*.whl

COPY kg-bridge/ .

CMD ["python", "main.py"]
