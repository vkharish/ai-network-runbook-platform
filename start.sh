#!/bin/bash
# Starts API + Celery worker in a tmux session with 3 panes.
# Ollama runs as a brew service in the background — no pane needed.
# Usage: ./start.sh

SESSION="runbook"
DIR="$(cd "$(dirname "$0")" && pwd)"

# Kill existing session if any
tmux kill-session -t $SESSION 2>/dev/null

# Pane 1: API server
tmux new-session -d -s $SESSION -x 220 -y 50
tmux send-keys -t $SESSION "cd $DIR && source .venv/bin/activate && make dev" Enter

# Pane 2: Celery worker (wait 3s for infra to start first)
tmux split-window -h -t $SESSION
tmux send-keys -t $SESSION "cd $DIR && source .venv/bin/activate && sleep 3 && make worker" Enter

# Pane 3: Shell for curl / testing
tmux split-window -v -t $SESSION:0.1
tmux send-keys -t $SESSION "cd $DIR && source .venv/bin/activate" Enter

# Attach
tmux attach-session -t $SESSION
