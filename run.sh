#!/usr/bin/env bash
# Atalho para rodar o Segundo Cérebro no Mac/Linux.
cd "$(dirname "$0")"
if [ ! -d ".venv" ]; then
  echo "Criando ambiente virtual (.venv)…"
  python3 -m venv .venv
fi
source .venv/bin/activate
pip install -q -r requirements.txt
python app.py
