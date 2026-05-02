"""
Remediation CLI — review and approve/reject AI-proposed commands from the terminal.

Usage:
  python3 scripts/remediation_cli.py --incident INC-0003
  python3 scripts/remediation_cli.py --incident INC-0003 --execute
  python3 scripts/remediation_cli.py --list-pending

Options:
  --incident   INC-XXXX number (e.g. INC-0003)
  --execute    After approvals, immediately trigger execution (ADMIN only)
  --list-pending   Show all incidents with pending remediation plans
  --url        API base URL (default: http://localhost:8000)
  --email      Login email
  --password   Login password
"""

import argparse
import json
import os
import sys
import textwrap

try:
    import requests
except ImportError:
    print("ERROR: requests library not found. Run: pip install requests")
    sys.exit(1)

# ── Colour helpers (terminal) ────────────────────────────────────────────────

def _c(code: str, text: str) -> str:
    """Wrap text in ANSI colour code."""
    codes = {
        "red": "\033[91m", "green": "\033[92m", "yellow": "\033[93m",
        "blue": "\033[94m", "cyan": "\033[96m", "bold": "\033[1m",
        "dim": "\033[2m", "reset": "\033[0m",
    }
    return f"{codes.get(code, '')}{text}{codes['reset']}"


RISK_COLOUR = {"low": "green", "medium": "yellow", "high": "red"}
STATUS_COLOUR = {
    "pending": "yellow", "approved": "green", "rejected": "red",
    "completed": "green", "failed": "red", "executing": "cyan",
}


# ── API client ───────────────────────────────────────────────────────────────

class APIClient:
    def __init__(self, base_url: str, token: str):
        self.base = base_url.rstrip("/")
        self.headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    def get(self, path: str) -> dict:
        r = requests.get(f"{self.base}{path}", headers=self.headers, timeout=10)
        r.raise_for_status()
        return r.json()

    def post(self, path: str, body: dict | None = None) -> dict:
        r = requests.post(f"{self.base}{path}", headers=self.headers,
                          json=body or {}, timeout=10)
        r.raise_for_status()
        return r.json()


def login(base_url: str, email: str, password: str) -> str:
    r = requests.post(
        f"{base_url.rstrip('/')}/api/v1/auth/login",
        json={"email": email, "password": password},
        timeout=10,
    )
    if r.status_code != 200:
        print(_c("red", f"Login failed: {r.text}"))
        sys.exit(1)
    return r.json()["access_token"]


# ── Display helpers ───────────────────────────────────────────────────────────

def _print_step(step: dict, idx: int) -> None:
    risk = step.get("risk_level", "low")
    approval = step.get("approval_status", "pending")
    exec_status = step.get("execution_status")

    risk_label = _c(RISK_COLOUR.get(risk, "reset"), f"[{risk.upper()} RISK]")
    approval_label = _c(STATUS_COLOUR.get(approval, "reset"), approval.upper())

    step_num = step["step_number"]
    print(f"\n  {_c('bold', f'Step {step_num}')}  {risk_label}  {approval_label}")
    print(f"  {'─' * 60}")
    print(f"  {_c('cyan', 'Device  :')} {step['device']}")
    print(f"  {_c('cyan', 'Command :')} {_c('bold', step['command'])}")
    print(f"  {_c('cyan', 'Why     :')} {step['rationale']}")
    print(f"  {_c('cyan', 'Expect  :')} {step['expected_outcome']}")

    if step.get("rejection_reason"):
        print(f"  {_c('red', 'Rejected:')} {step['rejection_reason']}")
    if step.get("approved_by"):
        verb = "Approved" if approval == "approved" else "Decided"
        by = step["approved_by"]
        at = (step.get("approved_at") or "")[:19]
        print(f"  {_c('dim', verb + ' by: ' + by + ' at ' + at)}")
    if exec_status:
        exec_label = _c(STATUS_COLOUR.get(exec_status, "reset"), exec_status.upper())
        print(f"  {_c('cyan', 'Exec    :')} {exec_label}")
    if step.get("execution_output"):
        preview = step["execution_output"][:300].replace("\n", "\n    ")
        print(f"  {_c('dim', 'Output  :')}\n    {preview}")


def _print_plan_header(plan: dict, inc_ref: str) -> None:
    status_colour = STATUS_COLOUR.get(plan["status"], "reset")
    print()
    print(_c("bold", f"{'═' * 64}"))
    print(_c("bold", f"  Remediation Plan — {inc_ref}"))
    print(f"  Status   : {_c(status_colour, plan['status'].upper())}")
    print(f"  Proposed : {plan['llm_provider']}")
    if plan.get("executed_at"):
        print(f"  Executed : {plan['executed_at'][:19]}")
    if plan.get("notes"):
        wrapped = textwrap.fill(plan["notes"], width=58, initial_indent="  ", subsequent_indent="  ")
        print(f"  Notes    :\n{wrapped}")
    print(_c("bold", f"{'═' * 64}"))


# ── Interactive approval loop ─────────────────────────────────────────────────

def interactive_review(client: APIClient, incident_id: str, inc_ref: str) -> None:
    """Walk the engineer through each pending step."""
    plan = client.get(f"/api/v1/incidents/{incident_id}/remediation")
    _print_plan_header(plan, inc_ref)

    pending = [s for s in plan["steps"] if s["approval_status"] == "pending"]
    already_decided = [s for s in plan["steps"] if s["approval_status"] != "pending"]

    if already_decided:
        print(f"\n  {_c('dim', f'{len(already_decided)} step(s) already decided:')}")
        for s in already_decided:
            _print_step(s, s["step_number"])

    if not pending:
        print(_c("green", "\n  All steps have been reviewed. Nothing pending."))
        _print_summary(plan)
        return

    print(f"\n  {_c('yellow', f'{len(pending)} step(s) awaiting your decision:')}")
    print(_c("dim", "  Commands: [a]pprove  [r]eject  [s]kip  [q]uit\n"))

    to_approve = []
    to_reject = []
    reject_reasons: dict[int, str] = {}

    for step in pending:
        _print_step(step, step["step_number"])

        while True:
            try:
                choice = input(
                    f"\n  Decision for Step {step['step_number']} "
                    f"({_c('green', 'a')}pprove / {_c('red', 'r')}eject / "
                    f"{_c('dim', 's')}kip / {_c('dim', 'q')}uit): "
                ).strip().lower()
            except (KeyboardInterrupt, EOFError):
                print("\n\nAborted.")
                sys.exit(0)

            if choice in ("a", "approve"):
                to_approve.append(step["step_number"])
                print(_c("green", "  ✓ Queued for approval"))
                break
            elif choice in ("r", "reject"):
                try:
                    reason = input("  Rejection reason (required): ").strip()
                except (KeyboardInterrupt, EOFError):
                    print("\n\nAborted.")
                    sys.exit(0)
                if not reason:
                    print(_c("red", "  Reason cannot be empty. Try again."))
                    continue
                to_reject.append(step["step_number"])
                reject_reasons[step["step_number"]] = reason
                print(_c("red", "  ✗ Queued for rejection"))
                break
            elif choice in ("s", "skip"):
                print(_c("dim", "  Skipped (remains pending)"))
                break
            elif choice in ("q", "quit"):
                print("\nQuitting — no changes sent yet.")
                sys.exit(0)
            else:
                print("  Invalid — type a, r, s, or q")

    # Send approvals
    if to_approve:
        print(f"\n  Sending approvals for steps: {to_approve} …", end="", flush=True)
        client.post(
            f"/api/v1/incidents/{incident_id}/remediation/approve",
            {"step_numbers": to_approve},
        )
        print(_c("green", " done"))

    # Send rejections (one call per unique reason, grouped)
    reason_groups: dict[str, list[int]] = {}
    for step_num, reason in reject_reasons.items():
        reason_groups.setdefault(reason, []).append(step_num)

    for reason, steps in reason_groups.items():
        print(f"  Sending rejections for steps: {steps} …", end="", flush=True)
        client.post(
            f"/api/v1/incidents/{incident_id}/remediation/reject",
            {"step_numbers": steps, "reason": reason},
        )
        print(_c("red", " done"))

    # Refresh and show summary
    plan = client.get(f"/api/v1/incidents/{incident_id}/remediation")
    _print_summary(plan)


def _print_summary(plan: dict) -> None:
    steps = plan["steps"]
    approved = [s for s in steps if s["approval_status"] == "approved"]
    rejected = [s for s in steps if s["approval_status"] == "rejected"]
    pending  = [s for s in steps if s["approval_status"] == "pending"]

    print()
    print(_c("bold", "  Summary"))
    print(f"  {_c('green',  f'Approved : {len(approved)}')}  "
          f"{_c('red',    f'Rejected : {len(rejected)}')}  "
          f"{_c('yellow', f'Pending  : {len(pending)}')}")

    if approved:
        print(f"\n  {_c('green', 'Approved steps ready for execution:')}")
        for s in approved:
            print(f"    Step {s['step_number']}: {s['command']}  [{s['device']}]")
        print(f"\n  {_c('dim', 'Ask an ADMIN to run:')}")
        print(f"  {_c('cyan', f'python3 scripts/remediation_cli.py --incident INC-XXXX --execute')}")
    print()


# ── Trigger execution ─────────────────────────────────────────────────────────

def trigger_execute(client: APIClient, incident_id: str, inc_ref: str) -> None:
    plan = client.get(f"/api/v1/incidents/{incident_id}/remediation")
    approved = [s for s in plan["steps"] if s["approval_status"] == "approved"]

    if not approved:
        print(_c("red", f"\n  No approved steps to execute on {inc_ref}."))
        print("  Run without --execute first to approve steps.")
        sys.exit(1)

    print(f"\n  {_c('yellow', f'About to execute {len(approved)} approved step(s) on live devices:')}")
    for s in approved:
        print(f"    Step {s['step_number']}: {_c('bold', s['command'])}  "
              f"[{s['device']}]  {_c(RISK_COLOUR.get(s['risk_level'], 'reset'), s['risk_level'])} risk")

    try:
        confirm = input(f"\n  {_c('bold', 'Confirm execution? [yes/no]: ')}").strip().lower()
    except (KeyboardInterrupt, EOFError):
        print("\nAborted.")
        sys.exit(0)

    if confirm not in ("yes", "y"):
        print("Execution cancelled.")
        sys.exit(0)

    print("\n  Triggering execution …", end="", flush=True)
    resp = client.post(f"/api/v1/incidents/{incident_id}/remediation/execute")
    print(_c("green", " started"))
    print(f"  Task ID : {resp.get('task_id', 'N/A')}")
    print(f"  Poll    : python3 scripts/remediation_cli.py --incident {inc_ref}")
    print()


# ── List pending plans ────────────────────────────────────────────────────────

def list_pending(client: APIClient) -> None:
    incidents = client.get("/api/v1/incidents/?status=awaiting_input")
    if not incidents:
        print(_c("green", "\n  No incidents awaiting input."))
        return

    print(_c("bold", "\n  Incidents with pending remediation:\n"))
    for inc in incidents:
        inc_ref = f"INC-{str(inc.get('incident_number', 0)).zfill(4)}"
        try:
            plan = client.get(f"/api/v1/incidents/{inc['id']}/remediation")
            pending_count = sum(1 for s in plan["steps"] if s["approval_status"] == "pending")
            approved_count = sum(1 for s in plan["steps"] if s["approval_status"] == "approved")
            plan_status = plan["status"]
        except Exception:
            continue

        status_c = STATUS_COLOUR.get(plan_status, "reset")
        print(f"  {_c('bold', inc_ref)}  {_c(status_c, plan_status.upper())}")
        print(f"    {inc['title'][:60]}")
        print(f"    Device: {inc.get('affected_device', 'N/A')}  "
              f"Severity: {inc.get('severity', 'N/A')}  "
              f"Steps: {_c('yellow', str(pending_count))} pending / "
              f"{_c('green', str(approved_count))} approved")
        print(f"    Run: python3 scripts/remediation_cli.py --incident {inc_ref}")
        print()


# ── Main ──────────────────────────────────────────────────────────────────────

def resolve_incident_id(client: APIClient, inc_ref: str) -> str:
    """Convert INC-0003 → UUID incident id."""
    # Strip prefix
    num_str = inc_ref.upper().replace("INC-", "").lstrip("0") or "0"
    try:
        inc_num = int(num_str)
    except ValueError:
        print(_c("red", f"Invalid incident reference: {inc_ref}"))
        sys.exit(1)

    incidents = client.get("/api/v1/incidents/")
    for inc in incidents:
        if inc.get("incident_number") == inc_num:
            return inc["id"]

    print(_c("red", f"Incident {inc_ref} not found."))
    sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Remediation CLI — approve/reject AI-proposed commands",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--incident", help="Incident reference, e.g. INC-0003")
    parser.add_argument("--execute", action="store_true", help="Trigger execution of approved steps (ADMIN)")
    parser.add_argument("--list-pending", action="store_true", help="List all incidents with pending plans")
    parser.add_argument("--url", default=os.getenv("RUNBOOK_URL", "http://localhost:8000"))
    parser.add_argument("--email", default=os.getenv("RUNBOOK_EMAIL", ""))
    parser.add_argument("--password", default=os.getenv("RUNBOOK_PASSWORD", ""))
    args = parser.parse_args()

    # Credentials — prompt if not set
    email = args.email
    password = args.password
    if not email:
        try:
            email = input("Email: ").strip()
        except (KeyboardInterrupt, EOFError):
            sys.exit(0)
    if not password:
        import getpass
        try:
            password = getpass.getpass("Password: ")
        except (KeyboardInterrupt, EOFError):
            sys.exit(0)

    print(f"\n  Connecting to {args.url} …", end="", flush=True)
    token = login(args.url, email, password)
    client = APIClient(args.url, token)
    print(_c("green", " OK"))

    if args.list_pending:
        list_pending(client)
        return

    if not args.incident:
        parser.print_help()
        sys.exit(0)

    inc_ref = args.incident.upper()
    if not inc_ref.startswith("INC-"):
        inc_ref = f"INC-{inc_ref.zfill(4)}"

    incident_id = resolve_incident_id(client, inc_ref)

    if args.execute:
        trigger_execute(client, incident_id, inc_ref)
    else:
        interactive_review(client, incident_id, inc_ref)


if __name__ == "__main__":
    main()
