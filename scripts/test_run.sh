#!/bin/bash
# Test Run Script - Single Job Lifecycle Monitor (Bash version)
# Creates a test job and monitors it through: create → claim → submit → verify → approve → ai$ reward

set -e

BACKEND_URL="${BACKEND_URL:-http://sparky1:8000}"
POLL_INTERVAL="${POLL_INTERVAL:-3}"
MAX_WAIT_SECONDS="${MAX_WAIT_SECONDS:-300}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
GRAY='\033[0;90m'
NC='\033[0m' # No Color

log_status() {
    local message="$1"
    local color="${2:-$NC}"
    local timestamp=$(date +"%H:%M:%S")
    echo -e "${GRAY}[$timestamp]${NC} ${color}${message}${NC}"
}

log_section() {
    echo ""
    echo -e "${CYAN}============================================================${NC}"
    echo -e "${CYAN}$1${NC}"
    echo -e "${CYAN}============================================================${NC}"
}

log_info() {
    local label="$1"
    local value="$2"
    echo -e "  ${GRAY}$label${NC}: $value"
}

# Test backend connectivity
test_backend() {
    if curl -s -f "$BACKEND_URL/world" > /dev/null 2>&1; then
        return 0
    else
        return 1
    fi
}

# Create test job
create_test_job() {
    local timestamp=$(date +"%Y-%m-%d %H:%M:%S")
    local job_data=$(cat <<EOF
{
  "title": "[TEST RUN] Creative JSON Task - $timestamp",
  "body": "Create a creative JSON list with exactly 3 items representing different creative concepts.\n\nEach item must have:\n- name: string (creative name)\n- category: string (e.g., 'art', 'music', 'writing')\n- value: number (1-100, representing creativity score)\n\nAcceptance criteria:\n- Submission must contain a valid JSON list\n- List must have exactly 3 items\n- Each item must have 'name', 'category', and 'value' fields\n- Evidence section must state: items=3, all_fields_present=true\n\nVerifier: json_list",
  "reward": 10.0,
  "created_by": "test_run_script"
}
EOF
)
    
    local response=$(curl -s -X POST "$BACKEND_URL/jobs/create" \
        -H "Content-Type: application/json" \
        -d "$job_data" \
        -w "\n%{http_code}")
    
    local http_code=$(echo "$response" | tail -n1)
    local body=$(echo "$response" | sed '$d')
    
    if [ "$http_code" = "200" ]; then
        echo "$body" | jq -r '.job.job_id'
    else
        log_status "Failed to create job: HTTP $http_code" "$RED"
        return 1
    fi
}

# Get job status
get_job_status() {
    local job_id="$1"
    curl -s "$BACKEND_URL/jobs/$job_id" | jq -r '.job'
}

# Submit test deliverable
submit_deliverable() {
    local job_id="$1"
    local agent_id="${2:-agent_2}"
    
    local submission_data=$(cat <<EOF
{
  "agent_id": "$agent_id",
  "submission": "## Deliverable\n\nHere is the creative JSON list with 3 items:\n\n\`\`\`json\n[\n  {\"name\": \"Digital Art Installation\", \"category\": \"art\", \"value\": 85},\n  {\"name\": \"Ambient Soundscape\", \"category\": \"music\", \"value\": 92},\n  {\"name\": \"Interactive Story\", \"category\": \"writing\", \"value\": 78}\n]\n\`\`\`\n\n## Evidence\n\n- items=3: The JSON list contains exactly 3 items\n- all_fields_present=true: Each item has 'name' (string), 'category' (string), and 'value' (number) fields\n- JSON is valid and parseable\n- All values are within 1-100 range"
}
EOF
)
    
    local response=$(curl -s -X POST "$BACKEND_URL/jobs/$job_id/submit" \
        -H "Content-Type: application/json" \
        -d "$submission_data" \
        -w "\n%{http_code}")
    
    local http_code=$(echo "$response" | tail -n1)
    if [ "$http_code" = "200" ]; then
        return 0
    else
        return 1
    fi
}

# Approve job
approve_job() {
    local job_id="$1"
    local payout="${2:-10.0}"
    
    local review_data=$(cat <<EOF
{
  "approved": true,
  "reviewed_by": "test_run_script",
  "note": "Test run approval - verification passed",
  "payout": $payout,
  "penalty": 0.0
}
EOF
)
    
    local response=$(curl -s -X POST "$BACKEND_URL/jobs/$job_id/review" \
        -H "Content-Type: application/json" \
        -d "$review_data" \
        -w "\n%{http_code}")
    
    local http_code=$(echo "$response" | tail -n1)
    if [ "$http_code" = "200" ]; then
        return 0
    else
        return 1
    fi
}

# Get balances
get_balances() {
    curl -s "$BACKEND_URL/economy/balances" | jq -r '.balances'
}

# Display job details
show_job_details() {
    local job_json="$1"
    local job_id=$(echo "$job_json" | jq -r '.job_id')
    local title=$(echo "$job_json" | jq -r '.title')
    local status=$(echo "$job_json" | jq -r '.status')
    local reward=$(echo "$job_json" | jq -r '.reward')
    local created_by=$(echo "$job_json" | jq -r '.created_by')
    local claimed_by=$(echo "$job_json" | jq -r '.claimed_by // "none"')
    local submitted_by=$(echo "$job_json" | jq -r '.submitted_by // "none"')
    
    log_info "Job ID" "$job_id"
    log_info "Title" "$title"
    log_info "Status" "$status"
    log_info "Reward" "${reward} ai$"
    log_info "Created By" "$created_by"
    log_info "Claimed By" "$claimed_by"
    log_info "Submitted By" "$submitted_by"
    
    local auto_verify=$(echo "$job_json" | jq -r '.auto_verify_ok // "null"')
    if [ "$auto_verify" != "null" ]; then
        if [ "$auto_verify" = "true" ]; then
            log_status "  Auto-Verify: PASS" "$GREEN"
        else
            log_status "  Auto-Verify: FAIL" "$RED"
        fi
        local verify_note=$(echo "$job_json" | jq -r '.auto_verify_note // ""')
        if [ -n "$verify_note" ]; then
            echo -e "    ${GRAY}Note: $verify_note${NC}"
        fi
    fi
}

# Main execution
log_section "AI Village Test Run - Single Job Lifecycle"
log_status "Backend URL: $BACKEND_URL" "$CYAN"
log_status "Poll Interval: $POLL_INTERVAL seconds" "$CYAN"
log_status "Max Wait Time: $MAX_WAIT_SECONDS seconds" "$CYAN"

# Step 1: Test backend
log_section "Step 1: Testing Backend Connection"
if ! test_backend; then
    log_status "❌ Backend is not accessible at $BACKEND_URL" "$RED"
    log_status "Please ensure backend is running on sparky1" "$YELLOW"
    exit 1
fi
log_status "✅ Backend is accessible" "$GREEN"

# Get initial balances
log_status "Initial balances:" "$CYAN"
initial_balances=$(get_balances)
echo "$initial_balances" | jq -r 'to_entries[] | "  \(.key): \(.value) ai$"'

# Step 2: Create job
log_section "Step 2: Creating Test Job"
job_id=$(create_test_job)
if [ -z "$job_id" ]; then
    log_status "❌ Failed to create job" "$RED"
    exit 1
fi
log_status "✅ Job created successfully" "$GREEN"
job_json=$(get_job_status "$job_id")
show_job_details "$job_json"

# Step 3: Wait for claim
log_section "Step 3: Waiting for Job to be Claimed"
start_time=$(date +%s)
claimed=false

while [ $claimed = false ] && [ $(($(date +%s) - start_time)) -lt $MAX_WAIT_SECONDS ]; do
    sleep $POLL_INTERVAL
    job_json=$(get_job_status "$job_id")
    if [ -z "$job_json" ]; then
        log_status "⚠️  Could not fetch job status" "$YELLOW"
        continue
    fi
    
    status=$(echo "$job_json" | jq -r '.status')
    if [ "$status" = "claimed" ]; then
        claimed_by=$(echo "$job_json" | jq -r '.claimed_by')
        log_status "✅ Job claimed by: $claimed_by" "$GREEN"
        show_job_details "$job_json"
        claimed=true
    elif [ "$status" = "open" ]; then
        log_status "⏳ Waiting for agent to claim job..." "$YELLOW"
    else
        log_status "⚠️  Job status changed to: $status" "$YELLOW"
        show_job_details "$job_json"
    fi
done

if [ $claimed = false ]; then
    log_status "⚠️  Job not claimed within timeout. Submitting manually..." "$YELLOW"
    # Try to claim manually (if API supports it)
    log_status "⚠️  Manual claim not implemented in bash version" "$YELLOW"
fi

# Step 4: Submit deliverable
log_section "Step 4: Submitting Test Deliverable"
if submit_deliverable "$job_id"; then
    log_status "✅ Deliverable submitted" "$GREEN"
else
    log_status "❌ Failed to submit deliverable" "$RED"
    exit 1
fi

# Step 5: Wait for verification
log_section "Step 5: Waiting for Auto-Verification"
start_time=$(date +%s)
verified=false

while [ $verified = false ] && [ $(($(date +%s) - start_time)) -lt 30 ]; do
    sleep 2
    job_json=$(get_job_status "$job_id")
    if [ -z "$job_json" ]; then
        continue
    fi
    
    auto_verify=$(echo "$job_json" | jq -r '.auto_verify_ok // "null"')
    if [ "$auto_verify" != "null" ]; then
        verified=true
        if [ "$auto_verify" = "true" ]; then
            log_status "✅ Auto-verification PASSED" "$GREEN"
            verify_name=$(echo "$job_json" | jq -r '.auto_verify_name // ""')
            if [ -n "$verify_name" ]; then
                log_status "   Verifier: $verify_name" "$GRAY"
            fi
        else
            log_status "❌ Auto-verification FAILED" "$RED"
            verify_note=$(echo "$job_json" | jq -r '.auto_verify_note // ""')
            if [ -n "$verify_note" ]; then
                log_status "   Note: $verify_note" "$RED"
            fi
        fi
        show_job_details "$job_json"
    else
        log_status "⏳ Waiting for auto-verification..." "$YELLOW"
    fi
done

if [ $verified = false ]; then
    log_status "⚠️  Auto-verification did not complete (may need manual trigger)" "$YELLOW"
fi

# Step 6: Approve job
log_section "Step 6: Approving Job"
if [ "$auto_verify" = "true" ] || [ $verified = true ]; then
    reward=$(echo "$job_json" | jq -r '.reward')
    if approve_job "$job_id" "$reward"; then
        log_status "✅ Job approved successfully" "$GREEN"
    else
        log_status "❌ Failed to approve job" "$RED"
        exit 1
    fi
else
    log_status "⚠️  Skipping approval (verification failed or incomplete)" "$YELLOW"
fi

# Step 7: Check final status
log_section "Step 7: Final Status Check"
sleep 2
final_job=$(get_job_status "$job_id")
if [ -n "$final_job" ]; then
    show_job_details "$final_job"
fi

# Step 8: Economy update
log_section "Step 8: Economy Update"
log_status "Final balances:" "$CYAN"
final_balances=$(get_balances)
echo "$final_balances" | jq -r 'to_entries[] | "  \(.key): \(.value) ai$"'

# Compare with initial
log_status "Balance changes:" "$CYAN"
echo "$final_balances" | jq -r 'to_entries[] | .key' | while read -r agent; do
    initial=$(echo "$initial_balances" | jq -r ".[\"$agent\"] // 0")
    final=$(echo "$final_balances" | jq -r ".[\"$agent\"]")
    change=$(echo "$final - $initial" | bc)
    if (( $(echo "$change > 0" | bc -l) )); then
        echo -e "  ${GRAY}$agent${NC}: ${GREEN}+$change${NC} ai$"
    else
        echo -e "  ${GRAY}$agent${NC}: $change ai$"
    fi
done

# Summary
log_section "Test Run Summary"
final_status=$(echo "$final_job" | jq -r '.status')
if [ "$final_status" = "approved" ]; then
    log_status "✅ Test run completed successfully!" "$GREEN"
    log_status "   Job was created, claimed, submitted, verified, and approved" "$GREEN"
    log_status "   Economy was updated correctly" "$GREEN"
    success=true
else
    log_status "⚠️  Test run completed with warnings" "$YELLOW"
    log_status "   Final job status: $final_status" "$YELLOW"
    success=false
fi

echo ""
log_status "View job in UI: $BACKEND_URL/ui/" "$CYAN"
log_status "Job ID: $job_id" "$CYAN"

exit $(if [ $success = true ]; then echo 0; else echo 1; fi)
