#!/usr/bin/env python3
"""End-to-end stdio smoke for Eclipse Orbit v0.1 (C0).

Temp state + temp drift file. Drives the real proxy process, which
spawns the shipped vendor_stub.py: initialize -> vendor_tools
(subsetting: export tool unclassified, delete withheld) -> masked
proxied read -> T2 call denied -> T2 call with bound token -> drift
raise -> refresh (HALT + notice receipt) -> halted call denied ->
owner halt_clear -> call works -> receipt_list (chain valid).
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).parent


def rpc(proc, rid, method, params=None):
    req = {"jsonrpc": "2.0", "id": rid, "method": method,
           "params": params or {}}
    proc.stdin.write(json.dumps(req) + "\n")
    proc.stdin.flush()
    return json.loads(proc.stdout.readline())


def call(proc, rid, name, args):
    response = rpc(proc, rid, "tools/call",
                   {"name": name, "arguments": args})
    return json.loads(response["result"]["content"][0]["text"])


def main():
    with tempfile.TemporaryDirectory() as tmp:
        drift = Path(tmp) / "drift.json"
        env = dict(os.environ)
        env["ECLIPSE_ORBIT_STATE"] = str(Path(tmp) / "state.json")
        env["ECLIPSE_ORBIT_STUB_DRIFT"] = str(drift)
        proc = subprocess.Popen(
            [sys.executable, str(HERE / "server.py")],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True,
            cwd=str(HERE), env=env)
        try:
            init = rpc(proc, 1, "initialize",
                       {"protocolVersion": "2025-03-26"})
            assert init["result"]["serverInfo"]["name"] == "eclipse-orbit"
            print("initialize OK (proxy spawned the stub vendor)")
            view = call(proc, 2, "vendor_tools", {})
            withheld = {w["name"]: w["reason"]
                        for w in view["withheld"]}
            assert withheld["crm_export_all"] == "UNCLASSIFIED"
            assert withheld["crm_delete_contact"] == \
                "CLASSIFIED_NOT_SURFACED_V1"
            print("subsetting OK: unclassified invisible; T3 vendor "
                  "tools classified but never surfaced")
            read = call(proc, 3, "vendor_call",
                        {"tool": "crm_search_contacts"})
            props = read["result"]["results"][0]["properties"]
            assert props["email"] == "***@acme.example", props
            print("proxied read OK, masked at egress")
            args = {"deal_id": "7001", "to_stage": "negotiation"}
            denied = call(proc, 4, "vendor_call", {
                "tool": "deal_stage_move", "arguments": args})
            assert "APPROVAL_REQUIRED" in denied["error"]
            print("T2 stage move without token DENIED OK")
            import hashlib

            def sha(t):
                return hashlib.sha256(t.encode()).hexdigest()

            def canon(o):
                return json.dumps(o, sort_keys=True,
                                  separators=(",", ":"))
            token = f"approve-call-deal_stage_move-" \
                    f"{sha(canon(args))[:12]}"
            moved = call(proc, 5, "vendor_call", {
                "tool": "deal_stage_move", "arguments": args,
                "approval_token": token})
            assert moved["result"]["status"] == "moved"
            print("T2 stage move with bound token OK")
            drift.write_text(json.dumps(
                {"raise": {"deal_stage_move": "T3"}}))
            view = call(proc, 6, "vendor_refresh", {})
            assert "deal_stage_move" in view["halted"], view
            print("DRIFT: vendor tier rise -> tool HALTED + notice "
                  "receipt OK")
            halted = call(proc, 7, "vendor_call", {
                "tool": "deal_stage_move", "arguments": args,
                "approval_token": token})
            assert "TOOL_HALTED_TIER_RISE" in halted["error"]
            print("halted call denied even with token OK")
            cleared = call(proc, 8, "halt_clear", {
                "tool": "deal_stage_move",
                "confirm_token": "clear-halt-deal_stage_move"})
            assert cleared["cleared"] == "deal_stage_move"
            moved = call(proc, 9, "vendor_call", {
                "tool": "deal_stage_move", "arguments": args,
                "approval_token": token})
            assert moved["result"]["status"] == "moved"
            print("owner halt_clear OK; acknowledged rise, tool "
                  "resumed")
            receipts = call(proc, 10, "receipt_list", {})
            assert receipts["chain_valid"]
            types = [r["type"] for r in receipts["receipts"]]
            assert "vendor_tier_rise_halt" in types
            assert "vendor_call_denied" in types
            blob = json.dumps(receipts)
            assert "maya.chen@acme.example" not in blob
            print("receipt_list OK: chain valid;", receipts["count"],
                  "receipts, zero content")
            print("SMOKE PASS")
        finally:
            proc.terminate()


if __name__ == "__main__":
    main()
