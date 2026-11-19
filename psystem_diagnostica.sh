#!/usr/bin/env bash
set -u

REPO="$HOME/P-System"
if [[ ! -d "$REPO/.git" ]]; then
  echo "ERRORE: repository non trovato in $REPO"
  exit 1
fi

cd "$REPO" || exit 1
OUT="$HOME/psystem-diagnostica-$(date +%Y%m%d-%H%M%S).txt"

{
  echo "P-SYSTEM - REPORT DIAGNOSTICO"
  echo "Data: $(date -Is)"
  echo "Percorso: $PWD"
  echo
  echo "===== GIT ====="
  git status --short --branch
  git log -5 --oneline
  echo
  echo "===== DIFFERENZE DA MAIN ====="
  git diff --stat main...HEAD 2>&1
  echo
  echo "===== STRUTTURA QUORUM ====="
  find network/quorum -maxdepth 2 -type f ! -path '*/__pycache__/*' 2>&1 | sort
  echo
  echo "===== TEST QUORUM PRESENTI ====="
  find tests -maxdepth 2 -type f \( -iname '*quorum*' -o -iname '*round*' \) 2>&1 | sort
  echo
  echo "===== RACCOLTA TEST ====="
  pytest --collect-only -q 2>&1
  echo
  echo "===== TEST SU QUORUM (SE PRESENTI) ====="
  for t in tests/test_quorum_driver.py tests/test_quorum_replica.py tests/test_quorum_sync.py tests/test_quorum_byzantine.py; do
    if [[ -f "$t" ]]; then
      echo "--- $t ---"
      pytest -q "$t" 2>&1
    fi
  done
  echo
  echo "===== FINE REPORT ====="
} >"$OUT" 2>&1

echo "Report creato: $OUT"
echo "Carica qui il file indicato."
