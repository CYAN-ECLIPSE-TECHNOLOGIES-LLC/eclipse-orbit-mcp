#!/usr/bin/env python3
"""LOCAL STUB 'vendor MCP' for Eclipse Orbit C0 — NOT a vendor server.

A stdlib JSON-RPC stdio process shaped like the official HubSpot MCP
server's tool surface (both wings: CRM objects + Service Hub
tickets), so the Orbit governing proxy can be built and benched
without contacting HubSpot or holding any credential. All data is
synthetic.

Drift fixtures (spec 8.6), driven by a JSON file whose path is in
$ECLIPSE_ORBIT_STUB_DRIFT, re-read on every tools/list:
  {"raise": {"deal_stage_move": "T3"}}   — a classified tool's
      vendor tier hint rises mid-flight;
  {"add_tools": [{"name": "crm_ai_summary", "tier_hint": "T1"}]}
      — a brand-new vendor tool appears, unclassified.
The base inventory already includes crm_export_all, a tool the
proxy has never classified: it must be invisible through the proxy
from the first call.
"""
import json
import os
import sys
from pathlib import Path

DRIFT_PATH = os.environ.get("ECLIPSE_ORBIT_STUB_DRIFT")

CONTACTS = [
    {"id": "1001", "properties": {
        "firstname": "Maya", "lastname": "Chen",
        "email": "maya.chen@acme.example",
        "phone": "+1-415-555-0134", "company": "Acme Example Corp"}},
    {"id": "1002", "properties": {
        "firstname": "Sam", "lastname": "Okafor",
        "email": "sam.okafor@globex.example",
        "phone": "+1-212-555-0176", "company": "Globex Example LLC"}},
]
COMPANIES = [
    {"id": "501", "properties": {
        "name": "Acme Example Corp", "domain": "acme.example",
        "industry": "logistics"}},
]
DEALS = [
    {"id": "7001", "properties": {
        "dealname": "Acme annual platform renewal", "amount": "48000",
        "dealstage": "qualification", "pipeline": "default"}},
]
TICKETS = [
    {"id": "9001", "properties": {
        "subject": "Invoice export fails with error 41",
        "content": "CSV export failed with error 41 since Tuesday.",
        "hs_pipeline_stage": "1", "hs_ticket_priority": "HIGH"}},
]

BASE_TOOLS = {
    "crm_search_contacts": "T0", "crm_get_contact": "T0",
    "crm_get_company": "T0", "crm_list_deals": "T0",
    "tickets_list": "T0", "ticket_get": "T0",
    "crm_create_note": "T1", "crm_create_task": "T1",
    "ticket_create": "T1",
    "ticket_reply_send": "T2", "deal_stage_move": "T2",
    "crm_delete_contact": "T3", "crm_bulk_update": "T3",
    # Present in the vendor inventory, never classified by the
    # proxy: must be invisible through Orbit (spec 8.6).
    "crm_export_all": "T1",
}


def drift():
    if DRIFT_PATH and Path(DRIFT_PATH).exists():
        try:
            return json.loads(Path(DRIFT_PATH).read_text())
        except Exception:
            return {}
    return {}


def tool_inventory():
    d = drift()
    hints = dict(BASE_TOOLS)
    for name, hint in (d.get("raise") or {}).items():
        if name in hints:
            hints[name] = hint
    tools = [{"name": name,
              "description": f"stub vendor tool {name}",
              "inputSchema": {"type": "object", "properties": {}},
              "_meta": {"tier_hint": hint}}
             for name, hint in hints.items()]
    for extra in d.get("add_tools") or []:
        tools.append({"name": extra["name"],
                      "description": "stub vendor tool (drift-added)",
                      "inputSchema": {"type": "object",
                                      "properties": {}},
                      "_meta": {"tier_hint": extra.get("tier_hint",
                                                        "T1")}})
    return tools


def call_tool(name, args):
    if name == "crm_search_contacts":
        return {"results": CONTACTS}
    if name == "crm_get_contact":
        for contact in CONTACTS:
            if contact["id"] == str(args.get("contact_id")):
                return contact
        return {"error": "not_found"}
    if name == "crm_get_company":
        return COMPANIES[0]
    if name == "crm_list_deals":
        return {"results": DEALS}
    if name == "tickets_list":
        return {"results": TICKETS}
    if name == "ticket_get":
        return TICKETS[0]
    if name in ("crm_create_note", "crm_create_task", "ticket_create"):
        return {"status": "created", "tool": name}
    if name == "ticket_reply_send":
        return {"status": "sent", "tool": name}
    if name == "deal_stage_move":
        return {"status": "moved", "deal_id": args.get("deal_id"),
                "to_stage": args.get("to_stage")}
    if name in ("crm_delete_contact", "crm_bulk_update"):
        return {"status": "executed", "tool": name}
    if name == "crm_export_all":
        return {"results": CONTACTS + COMPANIES}
    return {"status": "ok", "tool": name, "echo": args}


def handle(req):
    method, rid = req.get("method", ""), req.get("id")
    if method == "initialize":
        return {"jsonrpc": "2.0", "id": rid, "result": {
            "protocolVersion": "2025-03-26",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "stub-vendor-hubspot-shaped",
                           "version": "fixture-1"}}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": rid,
                "result": {"tools": tool_inventory()}}
    if method == "tools/call":
        name = req["params"]["name"]
        args = req["params"].get("arguments", {})
        known = {t["name"] for t in tool_inventory()}
        if name not in known:
            return {"jsonrpc": "2.0", "id": rid, "error": {
                "code": -32602, "message": f"unknown tool {name}"}}
        out = call_tool(name, args)
        return {"jsonrpc": "2.0", "id": rid, "result": {
            "content": [{"type": "text", "text": json.dumps(out)}]}}
    if rid is not None:
        return {"jsonrpc": "2.0", "id": rid, "error": {
            "code": -32601, "message": f"method not found: {method}"}}
    return None


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            response = handle(json.loads(line))
        except Exception as exc:
            response = {"jsonrpc": "2.0", "id": None, "error": {
                "code": -32603, "message": str(exc)}}
        if response is not None:
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
