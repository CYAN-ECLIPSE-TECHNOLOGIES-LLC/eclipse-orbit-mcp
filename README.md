# Eclipse Orbit MCP

**Powered by Cyan Eclipse Technologies** — https://cetech.ai

**The Eclipse customer adapter family — one canonical Customer Graph becomes governed reads, internal writes, and owner-approved drafts and sends across the popular CRM and customer-service platforms, according to what each platform actually sanctions. Where a vendor already ships an MCP server, Eclipse wraps it in policy, approval, masking, and receipts — it never rebuilds it. Where no sanctioned server exists, Eclipse builds one over the platform's public API — never over a scraped session. Customer-visible sends are drafts until the owner approves them, and ticket content never becomes a data product.**

## Why this exists

HubSpot ships an official MCP server (GA 2026-04-13) with read **and write** access across 12 object types — contacts, companies, deals, and Service Hub tickets in a single tool set. It is also, like every vendor server, an **ungoverned surface**: it acts as the signed-in user with that user's full permissions, and nothing in it asks a human before a deal stage moves or a ticket reply sends. Orbit is the governing proxy in front of it — Eclipse Orbit is the HubSpot adapter of the Eclipse customer adapter family (posture: **WRAP**, spec §11): one adapter, both wings, never a rebuilt HubSpot.

## Status — honest labels

v0.1.0, phase **C0 (fixture WRAP)**. Local stdio transport, Python stdlib only. The "vendor" in this build is a **local stub process** (`vendor_stub.py`) shaped like HubSpot's tool surface, including the drift fixtures. **No HubSpot server is contacted, no portal is connected, no credential exists, nothing is sent anywhere real, and no certification is claimed — bench pending.** The live wrap is C1, against the owner's own HubSpot account (the spec's recommended proving account: the free tier exercises both wings at zero license cost).

## What the proxy enforces

- **Classification registry.** Orbit pins a classified inventory of vendor tools, each with a tier and wing. A vendor tool the proxy has not classified is **invisible** to clients — calling one returns the same refusal as calling a tool that does not exist. Vendor tools classified T3 (delete, bulk update) are classified but **never surfaced in v1**.
- **Drift halt (§8.6).** Vendor servers change under their wraps — HubSpot added write access at GA. On every refresh, if a tool's vendor tier hint has **risen** above its classification, Orbit **halts the tool** and emits a notice receipt; even a valid approval token cannot move a halted tool. Halts are sticky: an owner clears one by name (`clear-halt-<tool>`), acknowledging that specific rise; a further rise halts again. If the vendor hint falls back, the halt auto-clears, receipted.
- **Approval gates (§6.3).** T2 vendor tools — `ticket_reply_send`, `deal_stage_move` — require an approval token bound to the tool name + the exact arguments hash. A token minted for one stage move does not authorize another.
- **Masking at egress.** Every vendor result passes the Deep Field masking pattern before crossing the proxy: emails domain-only on analytic surfaces, full on the owner surface; phones partial (last 2).
- **Receipts.** Every proxied call, denial, halt, and clear appends to a hash-chained ledger carrying tool names, tiers, and argument/result **hashes only** — never content.

## The declared gap

**HubSpot custom objects are not in the vendor server's tool set** (checked 2026-10-25, spec §11.4). Orbit declares them `invisible-through-MCP` (`object_gaps_declared` on every inventory view) and **never reaches around the vendor server with a parallel REST sidecar** — a wrap that quietly becomes a build has changed its posture without changing its label, which is exactly the drift this family's discipline exists to stop. Closing the gap is an owner decision (spec §24, Decision 6), informed by whether real data needs it.

## Tools (5)

| Tool | What it does |
|---|---|
| `vendor_tools` | The classified view: surfaced tools (tier + wing), withheld tools with reasons, active halts, declared OBJECT_GAPs. |
| `vendor_refresh` | Re-read the vendor inventory; apply the drift rules (new = unclassified, rise = halt + notice). |
| `vendor_call` | Proxied call: subsetting → halt check → tier gate → vendor → egress masking → receipt. |
| `halt_clear` | Owner act clearing one drift halt by name, acknowledging the rise. |
| `receipt_list` | Hash-chained ledger + chain verification. Names + hashes only, never content. |

The denylist is stated in code: no direct/unproxied vendor route, no REST sidecar, no custom-object reach-around, and no session/scraping route exists at any tier.

## Run it

```bash
python3 server.py            # MCP over stdio; spawns vendor_stub.py as the C0 vendor
python3 smoke.py             # end-to-end smoke over real stdio (temp state + drift file)
python3 -m unittest discover tests
```

State lives in `data/state.json` (override: `ECLIPSE_ORBIT_STATE`). The vendor command can be replaced (override: `ECLIPSE_ORBIT_VENDOR_CMD`); the stub's drift file is `$ECLIPSE_ORBIT_STUB_DRIFT`.

## Lineage

Spec: `~/workspace/cyan-eclipse/eclipse-customer-family-spec-20261025.md` (§§8.6, 11). Records feed **Eclipse Muster**, the family core. HubSpot keeps its brand; customer records belong to the account owner, worked under the owner's own HubSpot account. Nothing here implies HubSpot endorses Cyan Eclipse Technologies.
