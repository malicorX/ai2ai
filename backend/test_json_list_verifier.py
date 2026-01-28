#!/usr/bin/env python3
"""
Local test for json_list verifier extraction.
Run from backend dir (with deps):  pip install -q -r requirements.txt && python test_json_list_verifier.py
Verifies that the verifier uses the ```json block (or array-of-objects), not tag-like [run:...].
"""
import sys

# Run from backend/ so app is importable
try:
    from app.main import _auto_verify_task, Job
except ImportError:
    sys.path.insert(0, ".")
    from app.main import _auto_verify_task, Job


def _minimal_job(body: str, title: str = "Test") -> Job:
    return Job(
        job_id="test-id",
        title=title,
        body=body,
        reward=10.0,
        status="open",
        created_by="agent_1",
        created_at=0.0,
        claimed_by="",
        claimed_at=0.0,
        submitted_by="",
        submitted_at=0.0,
        submission="",
        reviewed_by="",
        reviewed_at=0.0,
        review_note="",
    )


def test_submission_with_run_tag_then_json_fence():
    """Submission has [run:...] first, then ```json block. Verifier must use the fence, not the tag."""
    body = (
        "[verifier:json_list]\n"
        "[json_required_keys:name,category,value]\n"
        "[json_min_items:3]\n"
        "Create a JSON list with 3 items."
    )
    # Realistic agent output: pasted task + deliverable in ```json
    submission = """Deliverable path: `/app/workspace/deliverables/x.md`

## Deliverable (markdown)

[run:20260127-163403]
[TEST_RUN_ID:abc-123]

## Output
## Deliverable
```json
[
  {"name": "Quantum Leap", "category": "fiction", "value": 85},
  {"name": "Superposition", "category": "science", "value": 92},
  {"name": "Entanglement Engine", "category": "technology", "value": 78}
]
```

## Evidence
- items=3
- all_fields_present=true
"""
    job = _minimal_job(body)
    out = _auto_verify_task(job, submission)
    assert out.ok, f"Expected pass, got: {out.note} {getattr(out, 'artifacts', {})}"
    assert "json list parsed" in (out.note or ""), out.note


def test_submission_array_of_objects_no_fence():
    """Submission has [run:...] and later [ { ... } ]. Verifier must use array-of-objects."""
    body = (
        "[verifier:json_list]\n"
        "[json_required_keys:name,category,value]\n"
        "[json_min_items:3]\n"
    )
    submission = """[run:20260127-163403]
Some text.
[ {"name":"A","category":"tech","value":50},{"name":"B","category":"science","value":60},{"name":"C","category":"fiction","value":70} ]
Evidence: items=3.
"""
    job = _minimal_job(body)
    out = _auto_verify_task(job, submission)
    assert out.ok, f"Expected pass, got: {out.note} {getattr(out, 'artifacts', {})}"


if __name__ == "__main__":
    test_submission_with_run_tag_then_json_fence()
    print("[OK] test_submission_with_run_tag_then_json_fence")
    test_submission_array_of_objects_no_fence()
    print("[OK] test_submission_array_of_objects_no_fence")
    print("All json_list verifier extraction tests passed.")
