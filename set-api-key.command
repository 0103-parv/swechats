#!/bin/bash
# Double-click to save a new Anthropic API key into ~/swechats/.env.
# Claude never sees the key — you paste it here, locally. Paste ONCE.
cd "$(dirname "$0")"
ENV="$HOME/swechats/.env"
while true; do
  echo "──────────────────────────────────────────────"
  echo "  Paste your Anthropic API key (sk-ant-...) ONE time,"
  echo "  then press Enter.  (Hidden — don't paste twice.)"
  echo "──────────────────────────────────────────────"
  read -rs KEY
  echo
  KEY="$(printf '%s' "$KEY" | tr -d '[:space:]')"      # strip stray spaces/newlines
  LEN=${#KEY}
  case "$KEY" in
    sk-ant-*) ;;
    *) echo "⚠️  That didn't start with sk-ant- (got $LEN chars). Let's try again."; echo; continue;;
  esac
  if [ "$LEN" -lt 90 ] || [ "$LEN" -gt 130 ]; then
    echo "⚠️  Got $LEN characters — a real key is ~108. Looks like a partial or DOUBLE paste."
    echo "    Try again and paste only once (Cmd+V a single time)."; echo; continue
  fi
  break
done
{ grep -v '^ANTHROPIC_API_KEY=' "$ENV" 2>/dev/null; echo "ANTHROPIC_API_KEY=$KEY"; } > "$ENV.tmp" && mv "$ENV.tmp" "$ENV"
echo "✅ Saved a $LEN-character key to ~/swechats/.env"
echo "Now go back to Claude and say \"saved\".  (You can close this window.)"
