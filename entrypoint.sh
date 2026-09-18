#!/bin/sh
# Container entry point.
#
#   QA_MODE=once    (default) run the suite, write the report, exit.
#                   Exit 0 means the suite passed — use this for a release gate.
#
#   QA_MODE=worker  stay up and watch REPORT_DIR/queue for job files. The React
#                   console drops a job file in to start a run. No Docker
#                   socket, no extra service.
#
#   QA_MODE=record  open a logged-in browser with Playwright's recorder on a
#                   virtual screen. Drive Odoo by hand at :6080; the clicks are
#                   written to /reports/recordings/<id>.py. That file is a
#                   DRAFT, not a test — see docs/rewrite-prompt.md.
set -e

REPORT_DIR="${REPORT_DIR:-/reports}"
ENV_NAME="${QA_ENV_NAME:-sit}"
SUITE="${QA_SUITE:-smoke}"
MODE="${QA_MODE:-once}"

echo ">> installing python packages"
pip install -q -r requirements.txt
# surface the version immediately — a mismatch with the image tag is the
# single most confusing failure in this setup
echo ">> $(python3 -m playwright --version 2>/dev/null || echo 'playwright version unknown')"

start_display() {
  [ "$QA_HEADLESS" = "false" ] || return 0
  VNC_PASSWORD="${QA_VNC_PASSWORD:-watchme}"
  echo ">> watch mode: installing virtual display (takes a minute)"
  apt-get update -qq
  apt-get install -y -qq xvfb x11vnc novnc websockify > /dev/null
  export DISPLAY=:99
  Xvfb :99 -screen 0 1600x900x24 > /dev/null 2>&1 &
  sleep 2
  x11vnc -display :99 -forever -shared -passwd "$VNC_PASSWORD" \
         -rfbport 5900 -quiet > /dev/null 2>&1 &
  websockify --web=/usr/share/novnc 6080 localhost:5900 > /dev/null 2>&1 &
  sleep 2
  echo ""
  echo "================================================================"
  echo "  WATCH IT LIVE"
  echo "  http://${QA_PUBLIC_HOST:-localhost}:6080/vnc.html"
  echo "  password: $VNC_PASSWORD"
  echo "================================================================"
  echo ""
}

if [ "$MODE" = "record" ]; then
  # Recording always needs a visible browser, whatever QA_HEADLESS says.
  QA_HEADLESS=false
  export QA_HEADLESS
  start_display
  echo ">> starting recorder"
  python3 record.py
  echo ">> recorder finished. Screen stays up for ${QA_WATCH_LINGER:-120}s."
  sleep "${QA_WATCH_LINGER:-120}"
  exit 0
fi

if [ "$MODE" = "worker" ]; then
  start_display
  echo ">> starting queue worker"
  exec python3 worker.py
fi

# ---- one-shot mode -------------------------------------------------------
export QA_RUN_ID="${QA_RUN_ID:-$(date -u +%Y-%m-%d_%H%M%S)}"
RUNS_DIR="$REPORT_DIR/$ENV_NAME/runs"
mkdir -p "$RUNS_DIR/$QA_RUN_ID"
echo ">> run id: $QA_RUN_ID"

KEEP="${QA_KEEP_RUNS:-20}"
OLD=$(ls -1 "$RUNS_DIR" 2>/dev/null | sort | head -n -"$KEEP")
if [ -n "$OLD" ]; then
  echo ">> pruning $(echo "$OLD" | wc -l) run(s) beyond the newest $KEEP"
  echo "$OLD" | while read -r d; do
    [ -n "$d" ] && rm -rf "$RUNS_DIR/$d"
  done
fi

start_display
[ "$QA_HEADLESS" = "false" ] && sleep "${QA_WATCH_DELAY:-45}"

set +e
pytest -m "$SUITE"
STATUS=$?
set -e

if [ "$QA_HEADLESS" = "false" ]; then
  LINGER="${QA_WATCH_LINGER:-120}"
  echo ">> tests finished (exit $STATUS). VNC stays open for ${LINGER}s."
  sleep "$LINGER"
fi

exit $STATUS
