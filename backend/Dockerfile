FROM python:3.12-slim

WORKDIR /app

# No compiler needed: psycopg2-binary and the other dependencies ship wheels.
# Dev image: includes pytest etc. (requirements-dev.txt pulls in requirements.txt).
COPY requirements.txt requirements-dev.txt ./
# Optional local wheelhouse (backend/wheels/, gitignored) for slow or flaky networks — fill it on
# the host with `pip download --platform manylinux2014_x86_64 --python-version 3.12
# --only-binary=:all: -d wheels -r requirements-dev.txt`. pip falls back to PyPI for anything missing.
COPY wheels/ /wheels/
# Generous retries/timeout: Docker Desktop's network can be flaky right after start-up.
# Offline from the wheelhouse first (otherwise pip still queries PyPI for every package).
RUN (pip install --no-cache-dir --no-index --find-links /wheels -r requirements-dev.txt \
     || pip install --no-cache-dir --retries 10 --timeout 120 --find-links /wheels -r requirements-dev.txt) \
    && rm -rf /wheels

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
