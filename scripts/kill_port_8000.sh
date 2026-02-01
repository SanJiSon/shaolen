#!/bin/bash
# Освобождает порт 8000 (убивает процессы, слушающие его)
echo "Поиск процессов на порту 8000..."
PID=$(lsof -ti:8000 2>/dev/null || fuser 8000/tcp 2>/dev/null | tr -d ' ')
if [ -n "$PID" ]; then
  echo "Найден процесс(ы): $PID"
  kill -9 $PID 2>/dev/null
  echo "Процесс(ы) завершены."
  sleep 1
else
  echo "Порт 8000 свободен."
fi
