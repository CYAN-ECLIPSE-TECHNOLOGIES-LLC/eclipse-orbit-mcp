#!/usr/bin/env python3
"""Eclipse Orbit v0.1 (C0) tests.
Run: python3 -m unittest discover tests

Orbit is driven over its real vendor link: each test spawns the
shipped vendor_stub.py as a subprocess (the local HubSpot-shaped
fixture server) and points the proxy at it.
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import server as S  # noqa: E402

HERE = Path(__file__).parent.parent


class OrbitCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.drift_path = str(Path(self.tmp.name) / "drift.json")
        self.client = S.VendorClient(
            [sys.executable, str(HERE / "vendor_stub.py")],
            env_extra={"ECLIPSE_ORBIT_STUB_DRIFT": self.drift_path})
        S.VENDOR = self.client
        self.state = S.empty_state()

    def tearDown(self):
        self.client.close()
        S.VENDOR = None
        self.tmp.cleanup()

    def set_drift(self, obj):
        Path(self.drift_path).write_text(json.dumps(obj))

    def call(self, tool, **kw):
        return S.t_vendor_call(self.state, {"tool": tool, **kw})


class TestSubsetting(OrbitCase):
    def test_unclassified_tool_invisible(self):
        view = S.t_vendor_tools(self.state, {})
        withheld = {w["name"]: w["reason"] for w in view["withheld"]}
        self.assertEqual(withheld.get("crm_export_all"),
                         "UNCLASSIFIED")
        self.assertEqual(withheld.get("crm_delete_contact"),
                         "CLASSIFIED_NOT_SURFACED_V1")
        surfaced = {t["name"] for t in view["surfaced"]}
        self.assertIn("crm_search_contacts", surfaced)
        self.assertNotIn("crm_export_all", surfaced)
        # Calling it is refused EXACTLY like a nonexistent tool.
        with self.assertRaises(S.ToolError) as ctx1:
            self.call("crm_export_all")
        with self.assertRaises(S.ToolError) as ctx2:
            self.call("crm_does_not_exist")
        self.assertEqual(str(ctx1.exception), str(ctx2.exception)
                         .replace("crm_does_not_exist",
                                  "crm_export_all"))
        with self.assertRaises(S.ToolError):
            self.call("crm_delete_contact")

    def test_object_gap_declared(self):
        view = S.t_vendor_tools(self.state, {})
        self.assertIn("hubspot_custom_objects",
                      view["object_gaps_declared"])


class TestProxiedCalls(OrbitCase):
    def test_masked_read_and_content_free_receipts(self):
        out = self.call("crm_search_contacts")
        props = out["result"]["results"][0]["properties"]
        self.assertEqual(props["email"], "***@acme.example")
        self.assertTrue(props["phone"].endswith("34"))
        owner = self.call("crm_search_contacts", surface="owner")
        self.assertEqual(
            owner["result"]["results"][0]["properties"]["email"],
            "maya.chen@acme.example")
        ledger = json.dumps(self.state["receipts"])
        self.assertNotIn("maya.chen@acme.example", ledger)
        self.assertNotIn("415-555-0134", ledger)
        self.assertTrue(
            S.verify_receipt_chain(self.state["receipts"]))

    def test_t2_gate_bound_token(self):
        args = {"deal_id": "7001", "to_stage": "negotiation"}
        with self.assertRaises(S.ToolError) as ctx:
            self.call("deal_stage_move", arguments=args)
        self.assertIn("APPROVAL_REQUIRED", str(ctx.exception))
        self.assertEqual(self.state["receipts"][-1]["type"],
                         "vendor_call_denied")
        token = S.expected_call_token("deal_stage_move", args)
        out = self.call("deal_stage_move", arguments=args,
                        approval_token=token)
        self.assertEqual(out["result"]["status"], "moved")
        # Token is bound to the exact arguments: different args fail.
        with self.assertRaises(S.ToolError):
            self.call("deal_stage_move",
                      arguments={"deal_id": "7001",
                                 "to_stage": "closedwon"},
                      approval_token=token)

    def test_t1_passes_without_token(self):
        out = self.call("ticket_create",
                        arguments={"subject": "fixture"})
        self.assertEqual(out["result"]["status"], "created")
        self.assertEqual(out["tier"], 1)


class TestDrift(OrbitCase):
    def test_tier_rise_halts_and_owner_clears(self):
        args = {"deal_id": "7001", "to_stage": "negotiation"}
        token = S.expected_call_token("deal_stage_move", args)
        out = self.call("deal_stage_move", arguments=args,
                        approval_token=token)
        self.assertEqual(out["result"]["status"], "moved")
        # The vendor raises the tool's tier mid-flight.
        self.set_drift({"raise": {"deal_stage_move": "T3"}})
        view = S.t_vendor_refresh(self.state, {})
        self.assertIn("deal_stage_move", view["halted"])
        halt_receipts = [r for r in self.state["receipts"]
                         if r["type"] == "vendor_tier_rise_halt"]
        self.assertEqual(len(halt_receipts), 1)
        self.assertEqual(
            halt_receipts[0]["detail"]["vendor_hint_tier"], 3)
        # Even a valid approval token cannot move a halted tool.
        with self.assertRaises(S.ToolError) as ctx:
            self.call("deal_stage_move", arguments=args,
                      approval_token=token)
        self.assertIn("TOOL_HALTED_TIER_RISE", str(ctx.exception))
        # Clearing is an owner act with its own token.
        with self.assertRaises(S.ToolError):
            S.t_halt_clear(self.state, {"tool": "deal_stage_move",
                                        "confirm_token": "nope"})
        S.t_halt_clear(self.state, {
            "tool": "deal_stage_move",
            "confirm_token": "clear-halt-deal_stage_move"})
        out = self.call("deal_stage_move", arguments=args,
                        approval_token=token)
        self.assertEqual(out["result"]["status"], "moved")
        # Refreshing again does not duplicate the halt notice for
        # the acknowledged rise.
        S.t_vendor_refresh(self.state, {})
        self.assertEqual(
            len([r for r in self.state["receipts"]
                 if r["type"] == "vendor_tier_rise_halt"]), 1)

    def test_new_tool_appears_unclassified(self):
        self.set_drift({"add_tools": [{"name": "crm_ai_summary",
                                       "tier_hint": "T1"}]})
        view = S.t_vendor_refresh(self.state, {})
        withheld = {w["name"]: w["reason"] for w in view["withheld"]}
        self.assertEqual(withheld.get("crm_ai_summary"),
                         "UNCLASSIFIED")
        with self.assertRaises(S.ToolError):
            self.call("crm_ai_summary")


class TestChain(OrbitCase):
    def test_chain_valid_and_tamper_detected(self):
        self.call("tickets_list")
        self.assertTrue(
            S.verify_receipt_chain(self.state["receipts"]))
        self.state["receipts"][0]["detail"]["verdict"] = "FORGED"
        self.assertFalse(
            S.verify_receipt_chain(self.state["receipts"]))

    def test_proxy_surface_is_exactly_five_tools(self):
        names = {t["name"] for t in S.tool_list()}
        self.assertEqual(names, {"vendor_tools", "vendor_refresh",
                                 "vendor_call", "halt_clear",
                                 "receipt_list"})
        for forbidden in S.FORBIDDEN_TOOL_NAMES:
            self.assertNotIn(forbidden, names)


if __name__ == "__main__":
    unittest.main()
