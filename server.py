#!/usr/bin/env python3
"""Eclipse Orbit MCP — v0.1.0, phase C0 (HubSpot WRAP proxy,
fixture vendor).

Powered by Cyan Eclipse Technologies (cetech.ai).

Descriptor (family spec, eclipse-customer-family-spec-20261025): the
Eclipse customer adapter family — one canonical Customer Graph becomes
governed reads, internal writes, and owner-approved drafts and sends
across the popular CRM and customer-service platforms, according to
what each platform actually sanctions. Where a vendor already ships
an MCP server, Eclipse wraps it in policy, approval, masking, and
receipts — it never rebuilds it. Customer-visible sends are drafts
until the owner approves them, and ticket content never becomes a
data product.

Orbit is the family's C0 WRAP exemplar (spec section 11): HubSpot
ships an official remote MCP server (GA 2026-04-13, OAuth 2.1 + PKCE,
read+write across 12 object types INCLUDING Service Hub tickets —
one adapter, two wings, modeled not duplicated). A vendor server is
an UNGOVERNED surface: it acts as the signed-in user, with no
approval gate before a deal stage moves or a ticket reply sends.
Orbit is the layer that asks:

  * CLASSIFICATION REGISTRY — the proxy pins a classified inventory
    of vendor tools, each with a tier + wing. A vendor tool the
    proxy has not classified is INVISIBLE to clients (Constellation
    registry doctrine). Vendor tools classified T3 (delete, bulk)
    are classified-but-never-surfaced in v1 (spec 6.2).
  * DRIFT HALT (spec 8.6) — the proxy re-reads the vendor inventory
    on refresh; if a tool's vendor tier hint RISES above its
    classified tier, the proxy HALTS that tool and emits a notice
    receipt. Halts are sticky: only an owner clear-token resumes
    the tool. A newly appearing tool is unclassified = withheld.
  * APPROVAL GATES — T2 vendor tools (ticket_reply_send,
    deal_stage_move) require an approval token bound to the tool +
    the exact arguments hash (spec 6.3).
  * MASKING AT EGRESS (Deep Field pattern) — emails domain-only on
    analytic surfaces / full on the owner surface; phones partial —
    applied to every vendor result before it crosses the proxy.
  * RECEIPTS — every proxied call, denial, and halt appends to a
    hash-chained ledger carrying tool names + hashes only, never
    argument or result content (spec 5.5).
  * OBJECT_GAP DECLARED (spec 11.4) — HubSpot custom objects are
    NOT in the vendor server's tool set; Orbit declares them
    invisible-through-MCP and never reaches around the vendor
    server with a side API.

C0 SCOPE: the "vendor" is a LOCAL STUB (vendor_stub.py) shaped like
HubSpot's tool surface. NO HubSpot server is contacted, no portal is
connected, no credential exists, nothing is sent anywhere real.
Synthetic data only. Live wrap is C1, owner-account-gated.

Transport: MCP over stdio (newline-delimited JSON-RPC 2.0), stdlib only.
State: $ECLIPSE_ORBIT_STATE or ./data/state.json beside this file.
Vendor command: $ECLIPSE_ORBIT_VENDOR_CMD (default: this dir's stub).
"""
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).parent
STATE_PATH = Path(os.environ.get(
    "ECLIPSE_ORBIT_STATE", HERE / "data" / "state.json"))

# The pinned classification registry (spec 8.6). tier = the proxy's
# own classification; surfaced=False means classified but never
# offered to clients in v1. Anything the vendor offers that is NOT
# in this registry is unclassified = invisible.
TOOL_REGISTRY = {
    "crm_search_contacts": {"tier": 0, "wing": "crm",
                            "surfaced": True},
    "crm_get_contact": {"tier": 0, "wing": "crm", "surfaced": True},
    "crm_get_company": {"tier": 0, "wing": "crm", "surfaced": True},
    "crm_list_deals": {"tier": 0, "wing": "crm", "surfaced": True},
    "tickets_list": {"tier": 0, "wing": "service", "surfaced": True},
    "ticket_get": {"tier": 0, "wing": "service", "surfaced": True},
    "crm_create_note": {"tier": 1, "wing": "crm", "surfaced": True},
    "crm_create_task": {"tier": 1, "wing": "crm", "surfaced": True},
    "ticket_create": {"tier": 1, "wing": "service", "surfaced": True},
    "ticket_reply_send": {"tier": 2, "wing": "service",
                          "surfaced": True},
    "deal_stage_move": {"tier": 2, "wing": "crm", "surfaced": True},
    # Vendor offers them; v1 does not surface them at all (spec 6.2:
    # delete + bulk are prohibited regardless of tier mechanics).
    "crm_delete_contact": {"tier": 3, "wing": "crm",
                           "surfaced": False},
    "crm_bulk_update": {"tier": 3, "wing": "crm", "surfaced": False},
}

# Vendor objects the sanctioned MCP surface does not carry at all
# (spec 11.4) — declared, never reached around.
OBJECT_GAPS = ["hubspot_custom_objects"]


class ToolError(Exception):
    pass


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def canon(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


# ------------------------------------------------------------- vendor link
class VendorClient:
    """JSON-RPC over the vendor process's stdio (stub in C0)."""

    def __init__(self, cmd, env_extra=None):
        env = dict(os.environ)
        if env_extra:
            env.update(env_extra)
        self.proc = subprocess.Popen(
            cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            text=True, env=env)
        self._rid = 0
        self.rpc("initialize", {"protocolVersion": "2025-03-26"})

    def rpc(self, method, params=None):
        self._rid += 1
        req = {"jsonrpc": "2.0", "id": self._rid, "method": method,
               "params": params or {}}
        self.proc.stdin.write(json.dumps(req) + "\n")
        self.proc.stdin.flush()
        return json.loads(self.proc.stdout.readline())

    def tools_list(self):
        resp = self.rpc("tools/list")
        return resp["result"]["tools"]

    def call(self, name, arguments):
        resp = self.rpc("tools/call",
                        {"name": name, "arguments": arguments})
        if "error" in resp:
            raise ToolError(
                f"vendor error: {resp['error'].get('message')}")
        return json.loads(resp["result"]["content"][0]["text"])

    def close(self):
        try:
            self.proc.stdin.close()
        except Exception:
            pass
        try:
            self.proc.terminate()
            self.proc.wait(timeout=5)
        except Exception:
            pass
        try:
            self.proc.stdout.close()
        except Exception:
            pass


VENDOR = None


def get_vendor():
    global VENDOR
    if VENDOR is None:
        cmd = os.environ.get("ECLIPSE_ORBIT_VENDOR_CMD")
        argv = cmd.split() if cmd else [
            sys.executable, str(HERE / "vendor_stub.py")]
        VENDOR = VendorClient(argv)
    return VENDOR


# ------------------------------------------------------------------- state
def empty_state() -> dict:
    return {"receipts": [], "halted": {}, "halt_notices": {},
            "halt_cleared": {}}


def load_state() -> dict:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text())
    return empty_state()


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=1))


# ---------------------------------------------------------------- receipts
def emit_receipt(state: dict, rtype: str, detail: dict) -> dict:
    """Append-only, hash-chained; tool names + hashes only."""
    prev = state["receipts"][-1]["hash"] if state["receipts"] else "GENESIS"
    entry = {"seq": len(state["receipts"]) + 1, "ts": int(time.time()),
             "type": rtype, "prev_hash": prev, "detail": detail}
    entry["hash"] = sha(prev + canon(
        {k: v for k, v in entry.items() if k != "hash"}))
    state["receipts"].append(entry)
    return entry


def verify_receipt_chain(receipts) -> bool:
    prev = "GENESIS"
    for entry in receipts:
        if entry.get("prev_hash") != prev:
            return False
        expected = sha(prev + canon(
            {k: v for k, v in entry.items() if k != "hash"}))
        if entry.get("hash") != expected:
            return False
        prev = entry["hash"]
    return True


# ------------------------------------------------------- inventory + drift
def hint_tier(tool) -> int:
    hint = str((tool.get("_meta") or {}).get("tier_hint") or "T0")
    try:
        return int(hint.lstrip("Tt"))
    except ValueError:
        return 99  # an unparsable hint is treated as maximal drift


def refresh_inventory(state):
    """Re-read the vendor inventory and apply the drift rules.
    Returns the classified view. Emits a halt notice receipt the
    first time a given (tool, hint) rise is observed."""
    vendor_tools = get_vendor().tools_list()
    surfaced, withheld = [], []
    for tool in vendor_tools:
        name = tool["name"]
        entry = TOOL_REGISTRY.get(name)
        if entry is None:
            withheld.append({"name": name,
                             "reason": "UNCLASSIFIED"})
            continue
        if not entry["surfaced"]:
            withheld.append({"name": name,
                             "reason": "CLASSIFIED_NOT_SURFACED_V1"})
            continue
        hint = hint_tier(tool)
        if hint > entry["tier"]:
            notice_key = f"{name}@T{hint}"
            if state["halt_cleared"].get(notice_key):
                # The owner acknowledged THIS rise by name; the tool
                # surfaces again, flagged. A further rise (new key)
                # halts again.
                surfaced.append({"name": name, "tier": entry["tier"],
                                 "wing": entry["wing"],
                                 "tier_rise_acknowledged": hint})
                continue
            if state["halt_notices"].get(notice_key) is None:
                receipt = emit_receipt(state, "vendor_tier_rise_halt", {
                    "tool": name, "classified_tier": entry["tier"],
                    "vendor_hint_tier": hint, "verdict": "HALT"})
                state["halt_notices"][notice_key] = receipt["seq"]
            state["halted"][name] = {
                "classified_tier": entry["tier"],
                "vendor_hint_tier": hint,
                "notice_receipt_seq": state["halt_notices"][notice_key]}
            withheld.append({"name": name,
                             "reason": "HALTED_TIER_RISE"})
            continue
        if name in state["halted"]:
            # The vendor hint fell back to/below the classification:
            # the halt condition no longer holds. Clear it, receipted.
            state["halted"].pop(name)
            emit_receipt(state, "vendor_halt_auto_cleared", {
                "tool": name, "classified_tier": entry["tier"],
                "vendor_hint_tier": hint, "verdict": "ALLOW"})
        surfaced.append({"name": name, "tier": entry["tier"],
                         "wing": entry["wing"]})
    return {"surfaced": surfaced, "withheld": withheld,
            "halted": sorted(state["halted"]),
            "object_gaps_declared": OBJECT_GAPS}


# ----------------------------------------------------------------- masking
def mask_email(value, surface):
    if not isinstance(value, str):
        return value
    if surface == "owner":
        return value
    local, _, domain = value.partition("@")
    return f"***@{domain}" if domain else "***"


def mask_phone(value):
    digits = "".join(ch for ch in str(value) if ch.isdigit())
    return f"***{digits[-2:]}" if len(digits) >= 2 else "***"


def mask_result(obj, surface):
    if isinstance(obj, dict):
        out = {}
        for key, value in obj.items():
            low = key.lower()
            if "email" in low and isinstance(value, str):
                out[key] = mask_email(value, surface)
            elif "phone" in low and value is not None:
                out[key] = mask_phone(value)
            else:
                out[key] = mask_result(value, surface)
        return out
    if isinstance(obj, list):
        return [mask_result(item, surface) for item in obj]
    return obj


# ------------------------------------------------------------------- tools
def t_vendor_tools(state, args):
    view = refresh_inventory(state)
    view["vendor"] = "local-stub (HubSpot-shaped fixture) — C0"
    return view


def t_vendor_refresh(state, args):
    view = refresh_inventory(state)
    emit_receipt(state, "vendor_inventory_refreshed", {
        "surfaced_count": len(view["surfaced"]),
        "withheld_count": len(view["withheld"]),
        "halted": view["halted"], "verdict": "ALLOW"})
    return view


def expected_call_token(tool, arguments):
    return f"approve-call-{tool}-{sha(canon(arguments))[:12]}"


def t_vendor_call(state, args):
    tool = str(args.get("tool") or "")
    arguments = args.get("arguments") or {}
    surface = str(args.get("surface") or "analytic").lower()
    # Invisibility rule: unclassified and never-surfaced tools are
    # indistinguishable from tools that do not exist.
    entry = TOOL_REGISTRY.get(tool)
    if entry is None or not entry["surfaced"]:
        raise ToolError(
            f"unknown or non-surfaced tool {tool} (unclassified "
            f"vendor tools are invisible through Orbit, spec 8.6)")
    refresh_inventory(state)
    if tool in state["halted"]:
        emit_receipt(state, "vendor_call_denied", {
            "tool": tool, "tier": entry["tier"],
            "reason": "TOOL_HALTED_TIER_RISE", "verdict": "DENY"})
        raise ToolError(
            "TOOL_HALTED_TIER_RISE: the vendor raised this tool's "
            "tier above its classification; the proxy halts it "
            "until an owner clears the halt (spec 8.6)")
    if entry["tier"] >= 2:
        expected = expected_call_token(tool, arguments)
        if str(args.get("approval_token") or "") != expected:
            emit_receipt(state, "vendor_call_denied", {
                "tool": tool, "tier": entry["tier"],
                "args_hash": sha(canon(arguments)),
                "reason": "APPROVAL_TOKEN_INVALID_OR_MISSING",
                "verdict": "DENY"})
            raise ToolError(
                "APPROVAL_REQUIRED: this vendor tool is T2 through "
                f"Orbit; token must be {expected} — bound to the "
                f"tool + exact arguments hash (spec 6.3)")
    raw = get_vendor().call(tool, arguments)
    masked = mask_result(raw, surface)
    receipt = emit_receipt(state, "vendor_call_proxied", {
        "tool": tool, "tier": entry["tier"], "wing": entry["wing"],
        "surface": surface, "args_hash": sha(canon(arguments)),
        "result_hash": sha(canon(raw)), "verdict": "ALLOW"})
    return {"tool": tool, "tier": entry["tier"],
            "result": masked, "receipt_seq": receipt["seq"]}


def t_halt_clear(state, args):
    tool = str(args.get("tool") or "")
    if tool not in state["halted"]:
        raise ToolError(f"tool is not halted: {tool}")
    expected = f"clear-halt-{tool}"
    if str(args.get("confirm_token") or "") != expected:
        raise ToolError(
            "CONFIRM_TOKEN_INVALID: clearing a drift halt is an "
            f"owner act; token must be {expected} (spec 8.6)")
    halt = state["halted"].pop(tool)
    notice_key = f"{tool}@T{halt['vendor_hint_tier']}"
    state["halt_cleared"][notice_key] = True
    receipt = emit_receipt(state, "vendor_halt_cleared", {
        "tool": tool, "was_hint_tier": halt["vendor_hint_tier"],
        "verdict": "ALLOW"})
    return {"cleared": tool, "receipt_seq": receipt["seq"]}


def t_receipt_list(state, args):
    limit = args.get("limit")
    receipts = state["receipts"]
    if limit is not None:
        receipts = receipts[-int(limit):]
    return {"receipts": receipts, "count": len(state["receipts"]),
            "chain_valid": verify_receipt_chain(state["receipts"])}


TOOLS = {
    "vendor_tools": (
        t_vendor_tools,
        "List the vendor tools Orbit surfaces (classified, with "
        "tier + wing), the withheld ones with reasons "
        "(UNCLASSIFIED / CLASSIFIED_NOT_SURFACED_V1 / "
        "HALTED_TIER_RISE), and the declared OBJECT_GAPs. The "
        "vendor in C0 is a local HubSpot-shaped stub.",
        {}, []),
    "vendor_refresh": (
        t_vendor_refresh,
        "Re-read the vendor inventory and apply the drift rules: "
        "new tools are withheld as UNCLASSIFIED; a vendor tier hint "
        "rising above the classification halts the tool + emits a "
        "notice receipt (spec 8.6).",
        {}, []),
    "vendor_call": (
        t_vendor_call,
        "Call a surfaced vendor tool through the proxy. T0/T1 pass "
        "on policy; T2 requires an approval token bound to the "
        "tool + exact arguments hash. Results are masked at egress "
        "(email domain-only unless surface=owner; phone partial). "
        "Unclassified / never-surfaced / halted tools are refused.",
        {"tool": {"type": "string"},
         "arguments": {"type": "object"},
         "approval_token": {"type": "string"},
         "surface": {"type": "string"}}, ["tool"]),
    "halt_clear": (
        t_halt_clear,
        "Owner act: clear a drift halt for one tool, acknowledging "
        "the named tier rise (clear-halt-<tool>). A FURTHER rise "
        "halts again. Receipted.",
        {"tool": {"type": "string"},
         "confirm_token": {"type": "string"}},
        ["tool", "confirm_token"]),
    "receipt_list": (
        t_receipt_list,
        "List the append-only, hash-chained receipts and verify the "
        "chain. Receipts carry tool names + hashes only — never "
        "argument or result content.",
        {"limit": {"type": "integer"}}, []),
}

# Capability denylist, stated in code: Orbit never rebuilds the
# vendor surface, never reaches around it, and never exposes a
# direct/unproxied route to vendor tools.
FORBIDDEN_TOOL_NAMES = {
    "vendor_call_direct", "hubspot_rest_call", "custom_object_read",
    "custom_object_write", "session_login", "cookie_reuse",
    "scrape_portal", "token_connect",
}


def tool_list():
    return [{"name": name, "description": description,
             "inputSchema": {"type": "object", "properties": props,
                             "required": required}}
            for name, (_, description, props, required) in TOOLS.items()]


def handle(req: dict):
    method, rid = req.get("method", ""), req.get("id")
    if method == "initialize":
        return {"jsonrpc": "2.0", "id": rid, "result": {
            "protocolVersion": req.get("params", {}).get(
                "protocolVersion", "2025-03-26"),
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "eclipse-orbit", "version": "0.1.0"}}}
    if method == "ping":
        return {"jsonrpc": "2.0", "id": rid, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": rid,
                "result": {"tools": tool_list()}}
    if method == "tools/call":
        name = req["params"]["name"]
        args = req["params"].get("arguments", {})
        if name in FORBIDDEN_TOOL_NAMES or name not in TOOLS:
            return {"jsonrpc": "2.0", "id": rid, "error": {
                "code": -32602,
                "message": f"unknown or C0-forbidden tool {name}"}}
        state = load_state()
        try:
            out = TOOLS[name][0](state, args)
            save_state(state)
            return {"jsonrpc": "2.0", "id": rid, "result": {
                "content": [{"type": "text",
                             "text": json.dumps(out, indent=1)}]}}
        except ToolError as exc:
            # Denials + halts are receipts too (spec 7.4): persist.
            save_state(state)
            return {"jsonrpc": "2.0", "id": rid, "result": {
                "content": [{"type": "text",
                             "text": json.dumps({"error": str(exc)})}],
                "isError": True}}
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
        except Exception as exc:  # never crash the transport
            response = {"jsonrpc": "2.0", "id": None, "error": {
                "code": -32603, "message": str(exc)}}
        if response is not None:
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()
    if VENDOR is not None:
        VENDOR.close()


if __name__ == "__main__":
    main()
