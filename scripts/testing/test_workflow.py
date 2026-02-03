#!/usr/bin/env python3
"""
End-to-end workflow test for AI Village system.

Tests the complete flow:
1. Backend health check
2. Create a test job
3. Agent claims job
4. Agent submits deliverable
5. Verify submission
6. Approve/reject job
7. Check ai$ economy
8. Verify learning patterns

Usage:
    python scripts/testing/test_workflow.py [--backend-url http://localhost:8000]
"""

import argparse
import json
import sys
import time
import requests
from typing import Optional, Dict, Any


class WorkflowTester:
    def __init__(self, backend_url: str = "http://localhost:8000"):
        self.backend_url = backend_url.rstrip("/")
        self.session = requests.Session()
        self.test_results = []
        
    def log(self, message: str, status: str = "INFO"):
        """Log a test step."""
        status_symbol = {
            "INFO": "ℹ️",
            "PASS": "✅",
            "FAIL": "❌",
            "WARN": "⚠️"
        }.get(status, "•")
        print(f"{status_symbol} {message}")
        self.test_results.append({"status": status, "message": message})
    
    def test_backend_health(self) -> bool:
        """Test 1: Backend is running and responsive."""
        self.log("Testing backend health...", "INFO")
        try:
            r = self.session.get(f"{self.backend_url}/world", timeout=5)
            if r.status_code == 200:
                self.log("Backend is healthy and responding", "PASS")
                return True
            else:
                self.log(f"Backend returned status {r.status_code}", "FAIL")
                return False
        except Exception as e:
            self.log(f"Backend health check failed: {e}", "FAIL")
            return False
    
    def test_create_job(self) -> Optional[str]:
        """Test 2: Create a simple, verifiable test job."""
        self.log("Creating test job...", "INFO")
        try:
            job_data = {
                "title": "[TEST] Simple JSON list task",
                "body": """Create a JSON list with exactly 3 items, each item should have:
- name: string
- value: number

Acceptance criteria:
- Submission must contain a JSON list
- List must have exactly 3 items
- Each item must have 'name' and 'value' fields
- Evidence section must state: items=3

Verifier: json_list""",
                "reward": 5.0,
                "created_by": "test_workflow"
            }
            r = self.session.post(
                f"{self.backend_url}/jobs/create",
                json=job_data,
                headers={"Content-Type": "application/json"},
                timeout=10
            )
            if r.status_code == 200:
                result = r.json()
                job_id = result.get("job", {}).get("job_id")
                if job_id:
                    self.log(f"Test job created: {job_id}", "PASS")
                    return job_id
                else:
                    self.log("Job created but no job_id returned", "FAIL")
                    return None
            else:
                self.log(f"Job creation failed: {r.status_code} - {r.text}", "FAIL")
                return None
        except Exception as e:
            self.log(f"Job creation error: {e}", "FAIL")
            return None
    
    def test_job_listing(self, job_id: str) -> bool:
        """Test 3: Verify job appears in listings."""
        self.log(f"Checking if job {job_id} appears in listings...", "INFO")
        try:
            r = self.session.get(f"{self.backend_url}/jobs?status=open&limit=100", timeout=5)
            if r.status_code == 200:
                jobs = r.json().get("jobs", [])
                found = any(j.get("job_id") == job_id for j in jobs)
                if found:
                    self.log(f"Job {job_id} found in open jobs list", "PASS")
                    return True
                else:
                    self.log(f"Job {job_id} not found in listings", "WARN")
                    return False
            else:
                self.log(f"Job listing failed: {r.status_code}", "FAIL")
                return False
        except Exception as e:
            self.log(f"Job listing error: {e}", "FAIL")
            return False
    
    def test_job_claim(self, job_id: str, agent_id: str = "agent_2") -> bool:
        """Test 4: Agent claims the job."""
        self.log(f"Testing job claim by {agent_id}...", "INFO")
        try:
            r = self.session.post(
                f"{self.backend_url}/jobs/{job_id}/claim",
                json={"agent_id": agent_id},
                headers={"Content-Type": "application/json"},
                timeout=10
            )
            if r.status_code == 200:
                result = r.json()
                if result.get("ok"):
                    self.log(f"Job {job_id} claimed successfully by {agent_id}", "PASS")
                    return True
                else:
                    error = result.get("error", "unknown")
                    if error == "already_claimed":
                        self.log(f"Job already claimed (expected if agent is running)", "WARN")
                        return True
                    else:
                        self.log(f"Job claim failed: {error}", "FAIL")
                        return False
            else:
                self.log(f"Job claim failed: {r.status_code} - {r.text}", "FAIL")
                return False
        except Exception as e:
            self.log(f"Job claim error: {e}", "FAIL")
            return False
    
    def test_job_submission(self, job_id: str, agent_id: str = "agent_2") -> bool:
        """Test 5: Submit a valid deliverable."""
        self.log(f"Submitting deliverable for job {job_id}...", "INFO")
        try:
            submission = """## Deliverable

Here is the JSON list with 3 items:

```json
[
  {"name": "alpha", "value": 10},
  {"name": "beta", "value": 20},
  {"name": "gamma", "value": 30}
]
```

## Evidence

- items=3: The JSON list contains exactly 3 items
- Each item has 'name' (string) and 'value' (number) fields
- JSON is valid and parseable
"""
            r = self.session.post(
                f"{self.backend_url}/jobs/{job_id}/submit",
                json={
                    "agent_id": agent_id,
                    "submission": submission
                },
                headers={"Content-Type": "application/json"},
                timeout=10
            )
            if r.status_code == 200:
                result = r.json()
                if result.get("ok"):
                    self.log(f"Job {job_id} submitted successfully", "PASS")
                    return True
                else:
                    self.log(f"Job submission failed: {result.get('error')}", "FAIL")
                    return False
            else:
                self.log(f"Job submission failed: {r.status_code} - {r.text}", "FAIL")
                return False
        except Exception as e:
            self.log(f"Job submission error: {e}", "FAIL")
            return False
    
    def test_auto_verification(self, job_id: str) -> bool:
        """Test 6: Check if auto-verification ran."""
        self.log(f"Checking auto-verification for job {job_id}...", "INFO")
        try:
            # Wait a moment for verification to run
            time.sleep(2)
            r = self.session.get(f"{self.backend_url}/jobs/{job_id}", timeout=5)
            if r.status_code == 200:
                job = r.json().get("job", {})
                auto_verify = job.get("auto_verify_ok")
                auto_verify_name = job.get("auto_verify_name", "")
                if auto_verify is True:
                    self.log(f"Auto-verification passed ({auto_verify_name})", "PASS")
                    return True
                elif auto_verify is False:
                    note = job.get("auto_verify_note", "")
                    self.log(f"Auto-verification failed: {note}", "FAIL")
                    return False
                else:
                    self.log("Auto-verification not yet run (may need manual trigger)", "WARN")
                    return False
            else:
                self.log(f"Failed to fetch job: {r.status_code}", "FAIL")
                return False
        except Exception as e:
            self.log(f"Auto-verification check error: {e}", "FAIL")
            return False
    
    def test_job_approval(self, job_id: str, reviewer: str = "test_workflow") -> bool:
        """Test 7: Approve the job."""
        self.log(f"Approving job {job_id}...", "INFO")
        try:
            r = self.session.post(
                f"{self.backend_url}/jobs/{job_id}/review",
                json={
                    "approved": True,
                    "reviewed_by": reviewer,
                    "note": "Test workflow approval",
                    "payout": 5.0,
                    "penalty": 0.0
                },
                headers={"Content-Type": "application/json"},
                timeout=10
            )
            if r.status_code == 200:
                result = r.json()
                if result.get("ok"):
                    self.log(f"Job {job_id} approved successfully", "PASS")
                    return True
                else:
                    self.log(f"Job approval failed: {result.get('error')}", "FAIL")
                    return False
            else:
                self.log(f"Job approval failed: {r.status_code} - {r.text}", "FAIL")
                return False
        except Exception as e:
            self.log(f"Job approval error: {e}", "FAIL")
            return False
    
    def test_economy_balance(self, agent_id: str = "agent_2") -> bool:
        """Test 8: Check agent balance after approval."""
        self.log(f"Checking ai$ balance for {agent_id}...", "INFO")
        try:
            r = self.session.get(f"{self.backend_url}/economy/balances", timeout=5)
            if r.status_code == 200:
                balances = r.json().get("balances", {})
                balance = balances.get(agent_id, 0.0)
                self.log(f"Agent {agent_id} balance: {balance} ai$", "PASS" if balance > 0 else "WARN")
                return True
            else:
                self.log(f"Failed to fetch balances: {r.status_code}", "FAIL")
                return False
        except Exception as e:
            self.log(f"Balance check error: {e}", "FAIL")
            return False
    
    def test_learning_patterns(self, agent_id: str = "agent_1") -> bool:
        """Test 9: Check if learning patterns are being stored."""
        self.log(f"Checking learning patterns for {agent_id}...", "INFO")
        try:
            r = self.session.get(f"{self.backend_url}/memory/{agent_id}/recent?limit=5", timeout=5)
            if r.status_code == 200:
                memories = r.json().get("memories", [])
                reflections = [m for m in memories if m.get("kind") == "reflection"]
                if reflections:
                    self.log(f"Found {len(reflections)} recent reflections (learning is active)", "PASS")
                    return True
                else:
                    self.log("No reflections found yet (agents may need time to learn)", "WARN")
                    return False
            else:
                self.log(f"Failed to fetch memories: {r.status_code}", "FAIL")
                return False
        except Exception as e:
            self.log(f"Learning patterns check error: {e}", "FAIL")
            return False
    
    def run_full_workflow(self) -> bool:
        """Run the complete end-to-end test workflow."""
        print("\n" + "="*60)
        print("AI Village Workflow Test")
        print("="*60 + "\n")
        
        all_passed = True
        
        # Test 1: Backend health
        if not self.test_backend_health():
            self.log("Cannot continue without backend", "FAIL")
            return False
        
        # Test 2: Create job
        job_id = self.test_create_job()
        if not job_id:
            self.log("Cannot continue without test job", "FAIL")
            return False
        
        # Test 3: Job listing
        self.test_job_listing(job_id)
        
        # Test 4: Job claim (may already be claimed by running agent)
        self.test_job_claim(job_id)
        
        # Test 5: Job submission
        if not self.test_job_submission(job_id):
            self.log("Cannot continue without submission", "FAIL")
            all_passed = False
        
        # Test 6: Auto-verification
        self.test_auto_verification(job_id)
        
        # Test 7: Job approval
        if not self.test_job_approval(job_id):
            self.log("Cannot continue without approval", "FAIL")
            all_passed = False
        
        # Test 8: Economy balance
        self.test_economy_balance()
        
        # Test 9: Learning patterns
        self.test_learning_patterns()
        
        # Summary
        print("\n" + "="*60)
        print("Test Summary")
        print("="*60)
        passed = sum(1 for r in self.test_results if r["status"] == "PASS")
        failed = sum(1 for r in self.test_results if r["status"] == "FAIL")
        warned = sum(1 for r in self.test_results if r["status"] == "WARN")
        total = len(self.test_results)
        
        print(f"Total tests: {total}")
        print(f"✅ Passed: {passed}")
        print(f"❌ Failed: {failed}")
        print(f"⚠️  Warnings: {warned}")
        print("="*60 + "\n")
        
        return all_passed and failed == 0


def main():
    parser = argparse.ArgumentParser(description="Test AI Village workflow end-to-end")
    parser.add_argument(
        "--backend-url",
        default="http://localhost:8000",
        help="Backend URL (default: http://localhost:8000)"
    )
    args = parser.parse_args()
    
    tester = WorkflowTester(backend_url=args.backend_url)
    success = tester.run_full_workflow()
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
