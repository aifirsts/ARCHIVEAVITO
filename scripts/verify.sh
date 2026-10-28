#!/usr/bin/env bash
# Полная проверка репозитория одной командой (то же, что делает CI).
#
#   bash scripts/verify.sh            # обязательные проверки + всё, что доступно
#   bash scripts/verify.sh --offline  # без сети: пропустить html-validate и npm
#
# Код возврата 0 — всё зелёное. Любая проваленная проверка печатается как FAIL
# и даёт ненулевой код возврата.
set -u -o pipefail

OFFLINE=0
[ "${1:-}" = "--offline" ] && OFFLINE=1

fail_count=0
skip_count=0
pass_count=0

pass() { printf '  ok    %s\n' "$1"; pass_count=$((pass_count + 1)); }
fail() { printf '  FAIL  %s\n' "$1"; fail_count=$((fail_count + 1)); }
skip() { printf '  skip  %s\n' "$1"; skip_count=$((skip_count + 1)); }

need() {
  printf '\n== %s\n' "$1"
}

PYTHON=${PYTHON:-python3}
[ -x .venv/bin/python ] && PYTHON=.venv/bin/python

if ! command -v "$PYTHON" >/dev/null 2>&1; then
  printf 'python не найден: %s\nУкажите интерпретатор: PYTHON=/путь/к/python bash scripts/verify.sh\n' "$PYTHON" >&2
  exit 2
fi

need "1/8 python и Pillow"
if "$PYTHON" - <<'PY'
import sys
try:
    import PIL
except ImportError:
    sys.exit(1)
PY
then pass "Pillow установлен ($($PYTHON -c 'import PIL; print(PIL.__version__)'))"
else fail "нет Pillow: python -m pip install -r requirements-dev.txt"; fi

need "2/8 пакет данных детерминирован (handoff)"
if "$PYTHON" handoff/generate.py >/dev/null 2>&1 && git diff --quiet -- handoff/storefront.json; then
  pass "handoff/storefront.json совпадает с генератором"
else
  fail "handoff/storefront.json устарел: python handoff/generate.py && git diff"
fi

need "3/8 сборки актуальны (site/public и зеркало docs/)"
if "$PYTHON" site/build.py --check; then pass "site/public и docs/ совпадают с источниками"
else fail "сборка устарела: python site/build.py"; fi

need "4/8 офлайн-тесты"
# вывод в файл, а не в конвейер: статус конвейера — это статус tail, а не тестов
if "$PYTHON" -m unittest discover -s tests >/tmp/unittest.log 2>&1; then
  tail -3 /tmp/unittest.log
  pass "$(grep -oE 'Ran [0-9]+ tests?' /tmp/unittest.log | tail -1) OK"
else
  fail "unittest (подробности: /tmp/unittest.log)"
  tail -20 /tmp/unittest.log
fi

need "5/8 синтаксис исходников"
if "$PYTHON" -m compileall -q avito_audit handoff site tests deploy; then pass "python компилируется"
else fail "ошибка компиляции python"; fi
if command -v node >/dev/null 2>&1; then
  if node --check site/src/app.js && node --check site/tests/dom/dom_smoke.js; then pass "JS синтаксис корректен"
  else fail "node --check"; fi
else
  skip "node не установлен"
fi

need "6/8 разметка: HTML5 + доступность"
if [ "$OFFLINE" = "1" ]; then
  skip "html-validate (офлайн-режим)"
elif command -v npx >/dev/null 2>&1; then
  if npx --yes html-validate@11 "site/public/**/*.html" && npx --yes html-validate@11 "docs/**/*.html"; then
    pass "18 страниц сайта и 18 страниц зеркала без ошибок разметки"
  else fail "html-validate"; fi
else
  skip "npx не установлен"
fi

need "7/8 поведение в headless DOM (jsdom)"
if [ "$OFFLINE" = "1" ]; then
  skip "dom_smoke (офлайн-режим)"
elif ! command -v npm >/dev/null 2>&1; then
  skip "npm не установлен"
else
  if [ ! -d site/tests/dom/node_modules ]; then
    npm install --prefix site/tests/dom --no-audit --no-fund --silent >/dev/null 2>&1 || true
  fi
  if [ -d site/tests/dom/node_modules/jsdom ]; then
    if node site/tests/dom/dom_smoke.js >/tmp/dom_smoke.log 2>&1; then
      pass "$(grep -c '  ok ' /tmp/dom_smoke.log) проверок поведения, 0 ошибок JS"
    else
      fail "dom_smoke (подробности: /tmp/dom_smoke.log)"; tail -15 /tmp/dom_smoke.log
    fi
    # the same markup served from a subdirectory, exactly like GitHub Pages
    if SITE_DIR=docs SITE_ORIGIN=https://aifirsts.github.io/MATRIX2/ node site/tests/dom/dom_smoke.js >/tmp/dom_smoke_pages.log 2>&1; then
      pass "$(grep -c '  ok ' /tmp/dom_smoke_pages.log) проверок зеркала в подкаталоге /MATRIX2/"
    else
      fail "dom_smoke зеркала (подробности: /tmp/dom_smoke_pages.log)"; tail -15 /tmp/dom_smoke_pages.log
    fi
  else
    skip "jsdom не установлен (npm install --prefix site/tests/dom)"
  fi
fi

need "8/8 план публикации на Porkbun"
if "$PYTHON" deploy/publish_porkbun.py --dry-run >/tmp/publish_plan.log 2>&1; then
  pass "$(head -2 /tmp/publish_plan.log | tail -1)"
else
  fail "deploy/publish_porkbun.py --dry-run"
fi

printf '\n─────────────────────────────────────────────\n'
printf 'пройдено: %s   пропущено: %s   провалено: %s\n' "$pass_count" "$skip_count" "$fail_count"
if [ "$fail_count" -ne 0 ]; then
  printf 'ИТОГ: есть ошибки — merge не рекомендуется.\n'
  exit 1
fi
printf 'ИТОГ: проверки пройдены, ветку можно мёржить.\n'
