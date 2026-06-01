#!/usr/bin/env bash
# Post-deploy + post-seed verification for Apple review demo accounts.
# Run after: (1) Render redeploys server.py, (2) create_demo_accounts.py runs.
#
# Usage:  bash verify_demo_accounts.sh

set -euo pipefail
BASE="https://greenhabit-backend.onrender.com/api"
DEMO_PASSWORD="${DEMO_PASSWORD:-GreenHabit2026!}"

pass() { echo "  ✅ $1"; }
fail() { echo "  ❌ $1"; }

echo ""
echo "=== Step 1: Login as reviewer@greenhabit.app ==="
RESPONSE=$(curl -s -X POST "$BASE/auth/email-login" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"reviewer@greenhabit.app\",\"password\":\"$DEMO_PASSWORD\"}")
echo "$RESPONSE" | python3 -m json.tool

TOKEN=$(echo "$RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['token'])" 2>/dev/null || true)
if [ -z "$TOKEN" ]; then
  fail "Login failed — cannot continue"; exit 1
fi
pass "Login OK — token obtained"

echo ""
echo "=== Step 2: Own profile (level must be non-null, guard does not fire) ==="
OWN=$(curl -s "$BASE/social/profile" -H "Authorization: Bearer $TOKEN")
LEVEL=$(echo "$OWN" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('level','MISSING'))")
if [ "$LEVEL" != "MISSING" ] && [ "$LEVEL" != "null" ]; then
  pass "Own profile OK — level=$LEVEL (guard won't throw privateProfile)"
else
  fail "Own profile missing level field — Bug 1 fix may have regressed"
fi

echo ""
echo "=== Step 3: Moderator bypass — view demo-explorer-001 without following ==="
EXPLORER=$(curl -s "$BASE/users/demo-explorer-001/profile" -H "Authorization: Bearer $TOKEN")
IS_PRIVATE=$(echo "$EXPLORER" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('isPrivate','absent'))")
EXP_LEVEL=$(echo "$EXPLORER" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('level','MISSING'))")

if [ "$IS_PRIVATE" = "absent" ] && [ "$EXP_LEVEL" != "MISSING" ]; then
  pass "Moderator bypass OK — full profile returned, isPrivate stripped, level=$EXP_LEVEL"
elif [ "$IS_PRIVATE" = "True" ] || [ "$IS_PRIVATE" = "true" ]; then
  fail "Moderator bypass STILL FAILING — got privacy stub (isModerator not set in DB?)"
  echo "  Hint: Re-run create_demo_accounts.py against production DB then retry."
else
  fail "Unexpected response: isPrivate=$IS_PRIVATE level=$EXP_LEVEL"
  echo "$EXPLORER" | python3 -m json.tool
fi

echo ""
echo "=== Step 4: Profanity filter — must return HTTP 422 (not 500) ==="
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE/tasks" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"title":"fucking save energy","details":"eco task","category":"Energy","estimatedImpact":"Saves 1kg CO2","date":"2026-05-31"}')
if [ "$HTTP_CODE" = "422" ]; then
  pass "Profanity filter returns HTTP 422"
elif [ "$HTTP_CODE" = "500" ]; then
  fail "Profanity filter still returning HTTP 500 — server.py not redeployed yet"
else
  fail "Unexpected HTTP $HTTP_CODE from profanity test"
fi

echo ""
echo "=== Step 5: Category validation — must return HTTP 422 ==="
CAT_CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE/tasks" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"title":"Test task","details":"d","category":"INVALID_HACK","estimatedImpact":"Saves 1kg CO2","date":"2026-05-31"}')
if [ "$CAT_CODE" = "422" ]; then
  pass "Category validation returns HTTP 422"
else
  fail "Category validation returned HTTP $CAT_CODE (expected 422)"
fi

echo ""
echo "=== All checks complete ==="
