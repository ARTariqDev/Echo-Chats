#!/bin/bash

echo "Starting process..."

export PATH=/usr/bin:$PATH

if [ "$#" -eq 1 ]; then
  PORT="$1"
else
  echo "No port provided. Searching for a free one..."
  PORT=$(comm -23 <(seq 3000 65000 | sort) <(ss -Htan | awk '{print $4}' | sed 's/.*://'))
  PORT=$(echo "$PORT" | shuf -n 1) 
  echo "Using free port: $PORT"
fi


if ! [[ "$PORT" =~ ^[0-9]+$ ]]; then
  echo "PORT must be a non-negative integer."
  exit 1
fi


PIDS=$(timeout 2s lsof -ti ":$PORT")
if [ -n "$PIDS" ]; then
  echo "Killing process on port $PORT..."
  kill -9 $PIDS
fi


if ! /usr/bin/git pull; then
  echo "git pull failed"
  exit 1
fi

# 32953 
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt


echo "Starting Flask app on port $PORT..."
exec gunicorn -b ":$PORT" app:app
