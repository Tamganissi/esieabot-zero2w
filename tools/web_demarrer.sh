#!/bin/bash
# Lance la commande web en arrière-plan. Usage : web_demarrer.sh [--simulation] [--duree N]
cd "$HOME/esieabot" || exit 1
pkill -f "venv/bin/python src/web\.py" 2>/dev/null
sleep 1
setsid nohup venv/bin/python src/web.py "$@" > /tmp/esieabot_web.log 2>&1 < /dev/null &
sleep 4
grep -o "CODE D.ACC.S : [0-9]*" /tmp/esieabot_web.log || tail -5 /tmp/esieabot_web.log
