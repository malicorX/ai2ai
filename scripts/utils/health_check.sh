#!/bin/bash
# Quick health check for AI Village system

BACKEND_URL="${BACKEND_URL:-http://localhost:8000}"

echo "🔍 AI Village Health Check"
echo "=========================="
echo "Backend URL: $BACKEND_URL"
echo ""

# Test 1: Backend health
echo "1. Testing backend health..."
if curl -s -f "$BACKEND_URL/world" > /dev/null; then
    echo "   ✅ Backend is responding"
else
    echo "   ❌ Backend is not responding"
    exit 1
fi

# Test 2: World state
echo "2. Testing world state..."
WORLD=$(curl -s "$BACKEND_URL/world")
if echo "$WORLD" | grep -q "agents"; then
    AGENT_COUNT=$(echo "$WORLD" | grep -o '"agents"' | wc -l || echo "0")
    echo "   ✅ World state accessible (agents: $AGENT_COUNT)"
else
    echo "   ⚠️  World state accessible but no agents found"
fi

# Test 3: Jobs endpoint
echo "3. Testing jobs endpoint..."
JOBS=$(curl -s "$BACKEND_URL/jobs?limit=10")
if echo "$JOBS" | grep -q "jobs"; then
    OPEN_COUNT=$(echo "$JOBS" | grep -o '"status":"open"' | wc -l || echo "0")
    echo "   ✅ Jobs endpoint working (open jobs: $OPEN_COUNT)"
else
    echo "   ❌ Jobs endpoint not working"
fi

# Test 4: Economy
echo "4. Testing economy endpoint..."
BALANCES=$(curl -s "$BACKEND_URL/economy/balances")
if echo "$BALANCES" | grep -q "balances"; then
    echo "   ✅ Economy endpoint working"
else
    echo "   ❌ Economy endpoint not working"
fi

# Test 5: Memory (agent_1)
echo "5. Testing memory endpoint (agent_1)..."
MEMORY=$(curl -s "$BACKEND_URL/memory/agent_1/recent?limit=1")
if echo "$MEMORY" | grep -q "memories"; then
    echo "   ✅ Memory endpoint working"
else
    echo "   ⚠️  Memory endpoint accessible but may be empty"
fi

# Test 6: Opportunities
echo "6. Testing opportunities endpoint..."
OPPS=$(curl -s "$BACKEND_URL/opportunities?limit=5")
if echo "$OPPS" | grep -q "items"; then
    echo "   ✅ Opportunities endpoint working"
else
    echo "   ⚠️  Opportunities endpoint accessible but may be empty"
fi

echo ""
echo "✅ Health check complete!"
echo ""
echo "For detailed testing, run:"
echo "  python scripts/testing/test_workflow.py --backend-url $BACKEND_URL"
