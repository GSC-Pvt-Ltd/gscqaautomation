#!/bin/sh
# Container entry point. Lives in the repo so the startup logic is readable
# and version-controlled, instead of buried in a YAML string.
#
# Headless (default)   : installs deps, runs the suite, exits.
# Watch (QA_HEADLESS=false) : also starts a virtual screen and noVNC so you can
#                        watch a real browser at http://<host>:6080/vnc.html
set -e

REPORT_DIR="${REPORT_DIR:-/reports}"
ENV_NAME="${QA_ENV_NAME:-sit}"
SUITE="${QA_SUITE:-smoke}"

echo ">> installing python packages"
pip install -q -r requirements.txt

# Each run gets its own folder. Exported so conftest.py uses the same id.
export QA_RUN_ID="${QA_RUN_ID:-$(date -u +%Y-%m-%d_%H%M%S)}"
RUNS_DIR="$REPORT_DIR/$ENV_NAME/runs"
mkdir -p "$RUNS_DIR/$QA_RUN_ID"
echo ">> run id: $QA_RUN_ID"

# Retention: keep the newest QA_KEEP_RUNS folders, delete older ones. Folder
# names are timestamps, so plain sort puts the oldest first.
KEEP="${QA_KEEP_RUNS:-20}"
OLD=$(ls -1 "$RUNS_DIR" 2>/dev/null | sort | head -n -"$KEEP")
if [ -n "$OLD" ]; then
  echo ">> pruning $(echo "$OLD" | wc -l) run(s) beyond the newest $KEEP"
  echo "$OLD" | while read -r d; do
    [ -n "$d" ] && rm -rf "$RUNS_DIR/$d"
  done
fi

if [ "$QA_HEADLESS" = "false" ]; then
  VNC_PASSWORD="${QA_VNC_PASSWORD:-watchme}"
  DELAY="${QA_WATCH_DELAY:-45}"

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
  echo "  tests start in ${DELAY}s"
  echo "================================================================"
  echo ""
  sleep "$DELAY"
fi

# don't let a failing test abort the script before the linger below
set +e
pytest -m "$SUITE"
STATUS=$?
set -e

if [ "$QA_HEADLESS" = "false" ]; then
  LINGER="${QA_WATCH_LINGER:-120}"
  echo ">> tests finished (exit $STATUS). VNC stays open for ${LINGER}s."
  sleep "$LINGER"
fi

# preserve the result so Exited(0) still means the suite passed
exit $STATUS
