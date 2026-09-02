# Mega Empires backend.
#
# Built and run under ROOTLESS Docker as the megaempires account, so there is no
# root anywhere in the deploy path. See deploy/README.md.

FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# The test gate lives in the build. An image whose tests fail never finishes, so
# a broken push cannot be deployed even by accident, and the container that is
# already running is not touched while the build runs.
#
# tests/test_ui.py skips itself here exactly as it does on the server today,
# because the image has no tkinter. Seeing skips is expected.
RUN python -m unittest discover -q

# No USER directive, deliberately. Under rootless Docker container UID 0 maps to
# the host user running the daemon (megaempires), so files written into the
# bind-mounted data directory come out owned by that account. A non-root
# container UID would map into the subuid range instead and the account could
# not read its own saves. "root" here is not host root.

# --timeout-graceful-shutdown is mandatory: /events is an infinite response, and
# without it uvicorn waits on open SSE streams and never exits.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--timeout-graceful-shutdown", "5"]
