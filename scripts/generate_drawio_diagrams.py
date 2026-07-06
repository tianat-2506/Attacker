from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from xml.dom import minidom
from xml.etree.ElementTree import Element, SubElement, tostring


ROOT_DIR = Path(__file__).resolve().parents[1]
OUTPUT = ROOT_DIR / "docs" / "diagrams" / "VietSupply_Radar_System_Blueprint.drawio"

COLORS = {
    "actor": ("#e8f1ff", "#2f5fb3"),
    "platform": ("#e9f8ef", "#2f7d4a"),
    "data": ("#fff4db", "#a66a00"),
    "risk": ("#ffe9e9", "#b33a3a"),
    "finance": ("#f0ecff", "#6b4db3"),
    "governance": ("#f5f5f5", "#666666"),
    "note": ("#fff9c4", "#b59b00"),
}

STYLES = {
    "title": "text;html=1;strokeColor=none;fillColor=none;fontSize=24;fontStyle=1;align=left;verticalAlign=middle;whiteSpace=wrap;",
    "subtitle": "text;html=1;strokeColor=none;fillColor=none;fontSize=12;fontColor=#4b5563;align=left;verticalAlign=top;whiteSpace=wrap;",
    "actor": "rounded=1;whiteSpace=wrap;html=1;arcSize=8;fontSize=12;fontStyle=1;fillColor=#e8f1ff;strokeColor=#2f5fb3;strokeWidth=2;",
    "platform": "rounded=1;whiteSpace=wrap;html=1;arcSize=8;fontSize=12;fillColor=#e9f8ef;strokeColor=#2f7d4a;strokeWidth=2;",
    "data": "shape=cylinder3d;boundedLbl=1;backgroundOutline=1;size=15;whiteSpace=wrap;html=1;fontSize=12;fillColor=#fff4db;strokeColor=#a66a00;strokeWidth=2;",
    "risk": "rounded=1;whiteSpace=wrap;html=1;arcSize=8;fontSize=12;fillColor=#ffe9e9;strokeColor=#b33a3a;strokeWidth=2;",
    "finance": "rounded=1;whiteSpace=wrap;html=1;arcSize=8;fontSize=12;fillColor=#f0ecff;strokeColor=#6b4db3;strokeWidth=2;",
    "governance": "rounded=1;whiteSpace=wrap;html=1;arcSize=8;fontSize=12;fillColor=#f5f5f5;strokeColor=#666666;strokeWidth=2;",
    "note": "shape=note;whiteSpace=wrap;html=1;backgroundOutline=1;fontSize=11;fillColor=#fff9c4;strokeColor=#b59b00;",
    "process": "rounded=1;whiteSpace=wrap;html=1;arcSize=8;fontSize=12;fillColor=#e9f8ef;strokeColor=#2f7d4a;strokeWidth=2;",
    "decision": "rhombus;whiteSpace=wrap;html=1;fontSize=11;fillColor=#fff4db;strokeColor=#a66a00;strokeWidth=2;",
    "start": "ellipse;whiteSpace=wrap;html=1;fontSize=12;fontStyle=1;fillColor=#e8f1ff;strokeColor=#2f5fb3;strokeWidth=2;",
    "end": "ellipse;whiteSpace=wrap;html=1;fontSize=12;fontStyle=1;fillColor=#f5f5f5;strokeColor=#666666;strokeWidth=2;",
    "class": "rounded=0;whiteSpace=wrap;html=1;fontSize=11;align=left;verticalAlign=top;spacing=8;fillColor=#ffffff;strokeColor=#334155;strokeWidth=2;",
    "edge": "endArrow=block;html=1;rounded=0;strokeWidth=2;edgeStyle=orthogonalEdgeStyle;fontSize=10;",
    "dashed_edge": "endArrow=block;html=1;rounded=0;strokeWidth=2;dashed=1;edgeStyle=orthogonalEdgeStyle;fontSize=10;",
    "lane": "swimlane;html=1;startSize=28;horizontal=1;fillColor=#f8fafc;strokeColor=#cbd5e1;fontColor=#334155;fontStyle=1;",
}


def br(text: str) -> str:
    return text.replace("\n", "<br>")


class Page:
    def __init__(self, mxfile: Element, name: str, width: int = 1800, height: int = 1200) -> None:
        diagram = SubElement(mxfile, "diagram", {"id": self.safe_id(name), "name": name})
        self.model = SubElement(
            diagram,
            "mxGraphModel",
            {
                "dx": "1422",
                "dy": "794",
                "grid": "1",
                "gridSize": "10",
                "guides": "1",
                "tooltips": "1",
                "connect": "1",
                "arrows": "1",
                "fold": "1",
                "page": "1",
                "pageScale": "1",
                "pageWidth": str(width),
                "pageHeight": str(height),
                "math": "0",
                "shadow": "0",
            },
        )
        self.root = SubElement(self.model, "root")
        SubElement(self.root, "mxCell", {"id": "0"})
        SubElement(self.root, "mxCell", {"id": "1", "parent": "0"})
        self.count = 0

    @staticmethod
    def safe_id(value: str) -> str:
        cleaned = "".join(ch if ch.isalnum() else "-" for ch in value.lower()).strip("-")
        return cleaned[:64]

    def next_id(self, prefix: str = "cell") -> str:
        self.count += 1
        return f"{Page.safe_id(prefix)}-{self.count}"

    def vertex(self, value: str, x: int, y: int, w: int, h: int, style: str, cell_id: str | None = None) -> str:
        cid = cell_id or self.next_id("v")
        cell = SubElement(
            self.root,
            "mxCell",
            {
                "id": cid,
                "value": br(value),
                "style": style,
                "vertex": "1",
                "parent": "1",
            },
        )
        SubElement(cell, "mxGeometry", {"x": str(x), "y": str(y), "width": str(w), "height": str(h), "as": "geometry"})
        return cid

    def edge(self, source: str, target: str, label: str = "", style: str | None = None, cell_id: str | None = None) -> str:
        cid = cell_id or self.next_id("e")
        cell = SubElement(
            self.root,
            "mxCell",
            {
                "id": cid,
                "value": br(label),
                "style": style or STYLES["edge"],
                "edge": "1",
                "parent": "1",
                "source": source,
                "target": target,
            },
        )
        SubElement(cell, "mxGeometry", {"relative": "1", "as": "geometry"})
        return cid

    def title(self, title: str, subtitle: str) -> None:
        self.vertex(title, 40, 24, 900, 34, STYLES["title"])
        self.vertex(subtitle, 42, 62, 1180, 52, STYLES["subtitle"])

    def legend(self, x: int, y: int) -> None:
        items = [
            ("Actor", "actor"),
            ("Platform", "platform"),
            ("Data", "data"),
            ("Risk/alert", "risk"),
            ("Finance", "finance"),
            ("Governance", "governance"),
        ]
        for idx, (label, key) in enumerate(items):
            fill, stroke = COLORS[key]
            style = f"rounded=1;whiteSpace=wrap;html=1;fontSize=10;fillColor={fill};strokeColor={stroke};"
            self.vertex(label, x + idx * 125, y, 110, 28, style)


def activity_page(
    mxfile: Element,
    name: str,
    subtitle: str,
    lanes: list[str],
    items: list[dict[str, object]],
    edges: list[tuple[str, str, str]],
    notes: list[tuple[str, int, int, int, int]] | None = None,
) -> None:
    max_col = max(int(item["col"]) for item in items)
    width = max(1800, 180 + (max_col + 1) * 220)
    height = 190 + len(lanes) * 170 + 160
    page = Page(mxfile, name, width, height)
    page.title(name, subtitle)
    page.legend(40, 116)

    lane_y = 170
    lane_h = 150
    for idx, lane in enumerate(lanes):
        page.vertex(lane, 40, lane_y + idx * 170, width - 100, lane_h, STYLES["lane"])

    node_ids: dict[str, str] = {}
    for item in items:
        key = str(item["key"])
        label = str(item["label"])
        kind = str(item.get("kind", "process"))
        lane = int(item["lane"])
        col = int(item["col"])
        w = int(item.get("w", 170))
        h = int(item.get("h", 70))
        x = 90 + col * 220
        y = lane_y + lane * 170 + 52
        if kind == "decision":
            w, h = 140, 90
            y -= 10
        node_ids[key] = page.vertex(label, x, y, w, h, STYLES[kind])

    for source, target, label in edges:
        page.edge(node_ids[source], node_ids[target], label)

    if notes:
        for text, x, y, w, h in notes:
            page.vertex(text, x, y, w, h, STYLES["note"])


def build_system_context(mxfile: Element) -> None:
    page = Page(mxfile, "01 System Context & Trust Boundary", 1800, 1160)
    page.title(
        "01 System Context & Trust Boundary",
        "VietSupply Radar is an advisory data intermediary. It gives risk signals, supplier shortlists and referral packages; humans and regulated partners make final decisions.",
    )
    page.legend(40, 116)

    platform_boundary = page.vertex(
        "<b>VietSupply Radar platform boundary</b>",
        420,
        180,
        860,
        560,
        "rounded=1;whiteSpace=wrap;html=1;arcSize=6;fillColor=#f8fafc;strokeColor=#64748b;strokeWidth=2;fontStyle=1;align=left;verticalAlign=top;spacing=10;",
    )
    frontend = page.vertex("React dashboard<br>Map / Sidebar / Risk panel", 480, 250, 200, 86, STYLES["platform"])
    api = page.vertex("FastAPI API<br>/graph /businesses /shock /recommendations", 780, 250, 260, 86, STYLES["platform"])
    services = page.vertex("Domain services<br>risk signal, matching, shock, invoice", 650, 410, 300, 96, STYLES["risk"])
    governance = page.vertex("Governance layer<br>RBAC, masking, consent, audit, dispute", 990, 410, 230, 96, STYLES["governance"])
    data = page.vertex("MVP CSV seed data<br>businesses, edges, financials, products, invoices", 620, 590, 330, 90, STYLES["data"])
    future = page.vertex("Future data sources<br>POS, ERP, accounting, e-invoice, bank, logistics", 990, 590, 230, 90, STYLES["data"])

    actors = [
        ("SME retailer<br>owns demand, financials, invoices", 70, 230),
        ("Supplier / distributor<br>owns capacity, terms, certifications", 70, 390),
        ("Manufacturer<br>views aggregate channel risk", 70, 550),
        ("Financial partner<br>underwrites independently", 1360, 310),
        ("Admin / demo operator<br>seed, reset, support", 1360, 500),
    ]
    actor_ids = [page.vertex(label, x, y, 230, 82, STYLES["actor"]) for label, x, y in actors]
    page.edge(actor_ids[0], frontend, "use dashboard")
    page.edge(actor_ids[1], frontend, "profile / accepted leads")
    page.edge(actor_ids[2], frontend, "aggregate network")
    page.edge(frontend, api, "JSON API")
    page.edge(api, services, "invoke pure functions")
    page.edge(api, governance, "access checks")
    page.edge(services, data, "read / compute")
    page.edge(future, governance, "consent + lineage")
    page.edge(governance, future, "validated import")
    page.edge(actor_ids[3], governance, "consented package only")
    page.edge(actor_ids[4], api, "synthetic admin ops")

    page.vertex(
        "<b>Guardrails</b><br>No auto supplier termination<br>No credit approval or loan decision<br>No legal breach/default declaration<br>No unmasked graph or financial data without consent",
        420,
        790,
        860,
        150,
        STYLES["note"],
    )
    page.vertex(
        "Trust boundary rule:<br>Public/demo views are masked. Private contact, invoice and financial data require purpose, consent and audit.",
        70,
        790,
        300,
        150,
        STYLES["governance"],
    )
    page.vertex(
        "Partner boundary:<br>Financial partners run their own KYB/KYC, underwriting and compliance review.",
        1360,
        790,
        300,
        150,
        STYLES["finance"],
    )
    # Keep the boundary cell behind its contents by referencing it in an invisible edge.
    page.edge(platform_boundary, frontend, "", "endArrow=none;html=1;strokeColor=none;")


def build_bounded_context(mxfile: Element) -> None:
    page = Page(mxfile, "02 Bounded Context Overview", 1800, 1160)
    page.title(
        "02 Bounded Context Overview",
        "Core business contexts plus cross-cutting governance. Governance is not a decoration; it gates sensitive visibility and commercial action.",
    )
    page.legend(40, 116)

    center = page.vertex("Evidence + Audit backbone<br>source refs, formula version, purpose, request id", 735, 495, 300, 110, STYLES["governance"])
    contexts = [
        ("SupplyGraph<br>Business, SupplyEdge, dependency", 450, 250, STYLES["platform"]),
        ("RiskIntelligence<br>Supply Risk Signal + drivers", 775, 250, STYLES["risk"]),
        ("SupplierMatching<br>shortlist + reason codes", 1100, 250, STYLES["platform"]),
        ("ShockSimulation<br>downstream impact scenario", 450, 720, STYLES["risk"]),
        ("InvoiceVerification<br>hash, funding status, alert", 775, 720, STYLES["finance"]),
        ("Governance<br>consent, RBAC, masking, dispute", 1100, 720, STYLES["governance"]),
    ]
    ids = [page.vertex(label, x, y, 250, 100, style) for label, x, y, style in contexts]
    for cid in ids:
        page.edge(cid, center, "evidence")
        page.edge(center, cid, "audit")
    page.edge(ids[0], ids[1], "dependency metrics")
    page.edge(ids[0], ids[3], "directed edges")
    page.edge(ids[1], ids[2], "risk filter")
    page.edge(ids[3], ids[2], "buyer need")
    page.edge(ids[4], ids[5], "consented invoice access")
    page.edge(ids[5], ids[2], "contact reveal gate")
    page.vertex(
        "Advisory wording:<br>RiskSignal, Suggested Alternatives, Introduction Request, Financial Partner Referral",
        90,
        850,
        330,
        130,
        STYLES["note"],
    )
    page.vertex(
        "Avoid wording:<br>Credit score, default probability, auto replacement, automatic loan approval, blockchain proves truth",
        1360,
        850,
        330,
        130,
        STYLES["note"],
    )


def build_activity_pages(mxfile: Element) -> None:
    activity_page(
        mxfile,
        "03 Activity - Onboarding & KYB Readiness",
        "From account setup to qualified profile. Pilot/production requires evidence and review before a supplier appears as viable.",
        ["SME / Supplier", "Platform", "Admin / Reviewer"],
        [
            {"key": "start", "label": "Start onboarding", "lane": 0, "col": 0, "kind": "start"},
            {"key": "org", "label": "Create organization<br>role + purpose", "lane": 0, "col": 1},
            {"key": "profile", "label": "Submit profile<br>products, terms, locations", "lane": 0, "col": 2},
            {"key": "docs", "label": "Upload evidence<br>certs, capacity, contracts", "lane": 0, "col": 3},
            {"key": "validate", "label": "Validate schema<br>dedupe + completeness", "lane": 1, "col": 4},
            {"key": "review", "label": "Qualification<br>review required?", "lane": 1, "col": 5, "kind": "decision"},
            {"key": "admin", "label": "KYB/KYC readiness<br>supplier qualification", "lane": 2, "col": 6},
            {"key": "active", "label": "Active masked profile<br>eligible for shortlist", "lane": 1, "col": 7, "kind": "end"},
        ],
        [
            ("start", "org", ""),
            ("org", "profile", ""),
            ("profile", "docs", ""),
            ("docs", "validate", ""),
            ("validate", "review", ""),
            ("review", "admin", "yes"),
            ("review", "active", "no / demo synthetic"),
            ("admin", "active", "approved"),
        ],
        [
            ("Guardrail: unverified supplier data can be used for demo only; pilot needs qualification and evidence trail.", 1180, 760, 360, 92)
        ],
    )

    activity_page(
        mxfile,
        "04 Activity - Data Import, Consent & Lineage",
        "Every sensitive import has a purpose, consent check, lineage record and audit event.",
        ["Data owner", "Platform data pipeline", "Governance"],
        [
            {"key": "start", "label": "Select data source<br>POS / ERP / e-invoice / logistics", "lane": 0, "col": 0, "kind": "start"},
            {"key": "purpose", "label": "Declare purpose<br>risk, matching, invoice check", "lane": 0, "col": 1},
            {"key": "consent", "label": "Consent valid?", "lane": 2, "col": 2, "kind": "decision"},
            {"key": "reject", "label": "Reject / request consent", "lane": 2, "col": 3, "kind": "end"},
            {"key": "ingest", "label": "Ingest file/API<br>checksum + source id", "lane": 1, "col": 3},
            {"key": "validate", "label": "Validate schema<br>range, FK, duplicates", "lane": 1, "col": 4},
            {"key": "lineage", "label": "Store lineage<br>raw ref + transform version", "lane": 2, "col": 5},
            {"key": "derived", "label": "Derived datasets<br>features, graph, invoice hash", "lane": 1, "col": 6},
            {"key": "audit", "label": "Audit event<br>who, purpose, request id", "lane": 2, "col": 7, "kind": "end"},
        ],
        [
            ("start", "purpose", ""),
            ("purpose", "consent", ""),
            ("consent", "reject", "no"),
            ("consent", "ingest", "yes"),
            ("ingest", "validate", ""),
            ("validate", "lineage", ""),
            ("lineage", "derived", ""),
            ("derived", "audit", ""),
        ],
        [("Raw financials and invoices stay private; public graph uses masked/aggregate views.", 1120, 755, 410, 84)],
    )

    activity_page(
        mxfile,
        "05 Activity - Supply Risk Signal",
        "Transparent rule-based signal with top drivers, evidence refs and explicit advisory wording.",
        ["Inputs", "Risk module", "Human / UI"],
        [
            {"key": "start", "label": "Financial snapshots<br>cash, AR/AP, debt, inventory", "lane": 0, "col": 0, "kind": "start"},
            {"key": "graph", "label": "Downstream edges<br>dependency count + volume", "lane": 0, "col": 1, "kind": "data"},
            {"key": "features", "label": "Normalize features<br>0-100 risk drivers", "lane": 1, "col": 2},
            {"key": "weighted", "label": "Weighted formula<br>risk-v1", "lane": 1, "col": 3},
            {"key": "drivers", "label": "Top drivers<br>cashflow, late payment, delivery", "lane": 1, "col": 4},
            {"key": "review", "label": "Needs review<br>or dispute?", "lane": 2, "col": 5, "kind": "decision"},
            {"key": "dispute", "label": "Evidence review<br>correct data or override note", "lane": 2, "col": 6},
            {"key": "publish", "label": "Show Supply Risk Signal<br>with advisory disclaimer", "lane": 2, "col": 7, "kind": "end"},
        ],
        [
            ("start", "features", ""),
            ("graph", "features", ""),
            ("features", "weighted", ""),
            ("weighted", "drivers", ""),
            ("drivers", "review", ""),
            ("review", "dispute", "yes"),
            ("dispute", "publish", "resolved"),
            ("review", "publish", "no"),
        ],
        [("Not a credit score, default probability, legal breach finding or automatic action trigger.", 1120, 755, 410, 84)],
    )

    activity_page(
        mxfile,
        "06 Activity - Shock Simulation",
        "Scenario simulation traverses directed supply edges and estimates downstream impact. It does not assert breach or fault.",
        ["User", "Shock module", "Output"],
        [
            {"key": "start", "label": "Select shock node<br>example BIZ-005", "lane": 0, "col": 0, "kind": "start"},
            {"key": "category", "label": "Choose product category<br>beverage, food, etc.", "lane": 0, "col": 1},
            {"key": "adj", "label": "Build adjacency<br>source -> target", "lane": 1, "col": 2},
            {"key": "bfs", "label": "BFS downstream<br>max depth + cycle guard", "lane": 1, "col": 3},
            {"key": "metrics", "label": "Compute impact<br>dependency, stockout, volume", "lane": 1, "col": 4},
            {"key": "map", "label": "Highlight affected nodes<br>red / yellow / green", "lane": 2, "col": 5},
            {"key": "shortlist", "label": "Trigger supplier shortlist<br>optional next step", "lane": 2, "col": 6, "kind": "end"},
        ],
        [
            ("start", "category", ""),
            ("category", "adj", ""),
            ("adj", "bfs", ""),
            ("bfs", "metrics", ""),
            ("metrics", "map", ""),
            ("map", "shortlist", ""),
        ],
        [("Scenario wording: use affected/at-risk/estimated stockout; avoid saying supplier breached or defaulted.", 1080, 755, 430, 84)],
    )

    activity_page(
        mxfile,
        "07 Activity - Supplier Shortlist & Introduction",
        "Matching ranks candidate suppliers, then gates real contact and commercial action behind review and mutual consent.",
        ["SME", "Matching module", "Supplier / Governance"],
        [
            {"key": "start", "label": "Buyer need<br>SKU/spec, volume, lead time", "lane": 0, "col": 0, "kind": "start"},
            {"key": "filter", "label": "Filter candidates<br>category, capacity, risk, lead time", "lane": 1, "col": 1},
            {"key": "score", "label": "Score components<br>product, capacity, distance, health, reliability, terms", "lane": 1, "col": 2},
            {"key": "top", "label": "Top 3 shortlist<br>reason codes", "lane": 1, "col": 3},
            {"key": "masked", "label": "Show masked cards<br>no private contact yet", "lane": 0, "col": 4},
            {"key": "intro", "label": "Request introduction?", "lane": 0, "col": 5, "kind": "decision"},
            {"key": "consent", "label": "Mutual consent<br>supplier accepts lead", "lane": 2, "col": 6},
            {"key": "rfq", "label": "RFQ / PO preview<br>human-approved", "lane": 0, "col": 7, "kind": "end"},
        ],
        [
            ("start", "filter", ""),
            ("filter", "score", ""),
            ("score", "top", ""),
            ("top", "masked", ""),
            ("masked", "intro", ""),
            ("intro", "consent", "yes"),
            ("consent", "rfq", "approved"),
        ],
        [("No auto replacement, no contract termination, no public customer list. Shortlist means decision support.", 1115, 755, 430, 84)],
    )

    activity_page(
        mxfile,
        "08 Activity - Contract & Assurance Review",
        "Before acting on a risk signal, users review terms, obligations and supplier assurance evidence.",
        ["SME / Buyer", "Platform evidence", "Legal / Operations review"],
        [
            {"key": "start", "label": "Risk signal or supply shock", "lane": 0, "col": 0, "kind": "start"},
            {"key": "contract", "label": "Collect contract terms<br>payment, MOQ, warranty, penalties, exclusivity", "lane": 1, "col": 1, "kind": "data"},
            {"key": "assurance", "label": "Collect assurance<br>certifications, samples, SLA, delivery history", "lane": 1, "col": 2, "kind": "data"},
            {"key": "status", "label": "Contract status?", "lane": 2, "col": 3, "kind": "decision"},
            {"key": "nobreach", "label": "No breach<br>monitor + contingency shortlist", "lane": 2, "col": 4},
            {"key": "suspected", "label": "Suspected breach<br>gather evidence + contact party", "lane": 2, "col": 5},
            {"key": "confirmed", "label": "Confirmed default<br>legal/ops decision outside platform", "lane": 2, "col": 6},
            {"key": "end", "label": "Human-approved next action", "lane": 0, "col": 7, "kind": "end"},
        ],
        [
            ("start", "contract", ""),
            ("start", "assurance", ""),
            ("contract", "status", ""),
            ("assurance", "status", ""),
            ("status", "nobreach", "no breach"),
            ("status", "suspected", "suspected"),
            ("status", "confirmed", "confirmed"),
            ("nobreach", "end", ""),
            ("suspected", "end", ""),
            ("confirmed", "end", ""),
        ],
        [("The platform may organize evidence, but does not declare breach/default or terminate contracts.", 1080, 755, 450, 84)],
    )

    activity_page(
        mxfile,
        "09 Activity - Financial Partner Referral",
        "The platform can package consented data for a partner. Underwriting and approval stay with the financial institution.",
        ["SME", "Platform", "Financial partner"],
        [
            {"key": "start", "label": "SME requests working capital option", "lane": 0, "col": 0, "kind": "start"},
            {"key": "consent", "label": "Consent to share<br>scope + expiry + purpose", "lane": 0, "col": 1},
            {"key": "package", "label": "Build data package<br>risk signal, cashflow summary, invoice status", "lane": 1, "col": 2},
            {"key": "audit", "label": "Audit export<br>request id + recipient", "lane": 1, "col": 3},
            {"key": "kyb", "label": "KYB/KYC + sanctions<br>partner process", "lane": 2, "col": 4},
            {"key": "underwrite", "label": "Underwriting<br>credit policy + docs", "lane": 2, "col": 5},
            {"key": "decision", "label": "Partner decision", "lane": 2, "col": 6, "kind": "decision"},
            {"key": "record", "label": "Record outcome metadata<br>no platform approval claim", "lane": 1, "col": 7, "kind": "end"},
        ],
        [
            ("start", "consent", ""),
            ("consent", "package", ""),
            ("package", "audit", ""),
            ("audit", "kyb", ""),
            ("kyb", "underwrite", ""),
            ("underwrite", "decision", ""),
            ("decision", "record", "approved / declined by partner"),
        ],
        [("Use referral / underwriting package. Avoid auto finance, loan approval or bank replacement claims.", 1100, 755, 450, 84)],
    )

    activity_page(
        mxfile,
        "10 Activity - Invoice Verification",
        "Hashing and funded-status checks reduce double-financing risk, but they do not prove the original invoice is true.",
        ["Seller / Buyer", "Invoice verification module", "Partner review"],
        [
            {"key": "start", "label": "Invoice submitted<br>seller, buyer, amount, due date", "lane": 0, "col": 0, "kind": "start"},
            {"key": "confirm", "label": "Buyer + seller confirmation", "lane": 0, "col": 1},
            {"key": "canonical", "label": "Canonical JSON<br>ignore mutable fields", "lane": 1, "col": 2},
            {"key": "hash", "label": "SHA-256 hash", "lane": 1, "col": 3},
            {"key": "funded", "label": "Existing funded hash?", "lane": 1, "col": 4, "kind": "decision"},
            {"key": "alert", "label": "Double-financing alert", "lane": 2, "col": 5, "kind": "risk"},
            {"key": "ok", "label": "Verification signal<br>no duplicate funded hash", "lane": 1, "col": 5},
            {"key": "partner", "label": "Partner reviews docs<br>KYB/KYC + invoice authenticity", "lane": 2, "col": 6, "kind": "end"},
        ],
        [
            ("start", "confirm", ""),
            ("confirm", "canonical", ""),
            ("canonical", "hash", ""),
            ("hash", "funded", ""),
            ("funded", "alert", "yes"),
            ("funded", "ok", "no"),
            ("alert", "partner", ""),
            ("ok", "partner", ""),
        ],
        [("Ledger/hash is tamper evidence after capture. It is not an oracle for truth of source documents.", 1080, 755, 460, 84)],
    )


def build_oop_class(mxfile: Element) -> None:
    page = Page(mxfile, "11 OOP Domain Class Diagram", 2200, 1500)
    page.title(
        "11 OOP Domain Class Diagram",
        "Conceptual domain model aligned with current MVP data and required pilot governance objects.",
    )
    page.legend(40, 116)

    def cls(name: str, attrs: list[str], x: int, y: int, style: str = STYLES["class"]) -> str:
        label = "<b>" + name + "</b><hr>" + "<br>".join(attrs)
        return page.vertex(label, x, y, 250, 150, style)

    org = cls("Organization", ["organization_id", "name", "type", "status"], 60, 210)
    user = cls("User", ["user_id", "email", "role", "organization_id"], 60, 420)
    role = cls("Role / Permission", ["role", "scope", "allowed_actions"], 60, 630, STYLES["governance"])

    business = cls("Business", ["business_id", "name/display_name", "type", "province", "lat/lng", "financial_health_score"], 430, 260)
    product = cls("Product", ["sku", "product_name", "category", "specification", "available_capacity", "certifications"], 430, 500)
    financial = cls("FinancialSnapshot", ["business_id", "month", "cash_in/out", "revenue", "debt", "AR/AP", "inventory_value"], 430, 740, STYLES["data"])
    edge = cls("SupplyEdge", ["edge_id", "source_id", "target_id", "product_category", "monthly_volume", "lead_time_days", "reliability", "payment_term_days"], 800, 260)
    risk = cls("RiskSignal", ["score", "level", "drivers", "formula_version", "evidence_refs", "calculated_at"], 800, 520, STYLES["risk"])
    driver = cls("RiskDriver", ["feature", "value", "weight", "contribution", "message"], 800, 760, STYLES["risk"])

    rec = cls("SupplierRecommendation", ["buyer_id", "candidate_supplier_id", "match_score", "components", "reason_codes", "new_edge_preview"], 1180, 260)
    invoice = cls("InvoiceVerification", ["invoice_id", "seller_id", "buyer_id", "amount", "invoice_hash", "funding_status", "confirmed_by"], 1180, 520, STYLES["finance"])
    evidence = cls("EvidencePackage", ["package_id", "source_refs", "calculation_version", "purpose", "created_at"], 1180, 780, STYLES["governance"])

    consent = cls("ConsentRecord", ["actor_id", "subject_id", "scope", "purpose", "expires_at", "revoked_at"], 1560, 260, STYLES["governance"])
    audit = cls("AuditLog", ["event_type", "actor_role", "subject_id", "purpose", "timestamp", "request_id"], 1560, 520, STYLES["governance"])
    dispute = cls("DisputeCase", ["case_id", "subject_id", "claim", "evidence_refs", "status", "resolution"], 1560, 780, STYLES["governance"])

    page.edge(org, user, "1..n")
    page.edge(user, role, "has")
    page.edge(org, business, "owns / operates")
    page.edge(business, product, "1..n")
    page.edge(business, financial, "1..n")
    page.edge(business, edge, "source/target")
    page.edge(edge, risk, "dependency metrics")
    page.edge(financial, risk, "financial features")
    page.edge(risk, driver, "1..n")
    page.edge(risk, rec, "risk filter")
    page.edge(business, rec, "buyer + supplier")
    page.edge(business, invoice, "seller/buyer")
    page.edge(invoice, evidence, "source refs")
    page.edge(evidence, risk, "explains")
    page.edge(evidence, rec, "supports")
    page.edge(consent, invoice, "gates access")
    page.edge(consent, rec, "gates contact")
    page.edge(audit, consent, "records")
    page.edge(dispute, evidence, "reviews")
    page.edge(dispute, risk, "may revise")

    page.vertex(
        "Naming note:<br>Code may keep numeric field `score`, but user-facing entity is RiskSignal / Early Warning Signal.",
        60,
        1020,
        530,
        100,
        STYLES["note"],
    )


def build_service_component(mxfile: Element) -> None:
    page = Page(mxfile, "12 Service Component & Runtime Dataclass Graph", 2200, 1500)
    page.title(
        "12 Service Component & Runtime Dataclass Graph",
        "Current MVP code is pure Python domain functions behind FastAPI, with target governance services shown as required pilot guardrails.",
    )
    page.legend(40, 116)

    ui = [
        ("App.tsx<br>selectedId + shock state", 80, 240),
        ("MapView<br>nodes + edges + selected event", 80, 410),
        ("Sidebar<br>business detail + tabs", 80, 580),
        ("RiskPanel / RecommendationCard / ShockButton", 80, 750),
    ]
    ui_ids = [page.vertex(label, x, y, 270, 90, STYLES["platform"]) for label, x, y in ui]

    api = page.vertex("FastAPI main.py<br>health, businesses, graph, shock, recommendations", 460, 410, 310, 120, STYLES["platform"])
    loader = page.vertex("data_loader.py<br>load CSV into dict/list repositories", 460, 650, 310, 100, STYLES["data"])
    csv = page.vertex("CSV datasets<br>businesses, supply_edges, financials, products, invoices", 460, 850, 310, 110, STYLES["data"])

    risk = page.vertex("risk_scoring.py<br>RiskDriver, RiskResult<br>features_from_financials -> score_from_features", 900, 220, 340, 130, STYLES["risk"])
    matching = page.vertex("supplier_matching.py<br>SupplierRecommendation<br>rank_suppliers", 900, 420, 340, 130, STYLES["platform"])
    shock = page.vertex("shock_simulation.py<br>AffectedNode, ShockImpact, ShockResult<br>simulate_shock", 900, 620, 340, 130, STYLES["risk"])
    invoice = page.vertex("invoice_verification.py<br>canonical_invoice, invoice_hash,<br>double_financing_alert", 900, 820, 340, 130, STYLES["finance"])

    gov = page.vertex("Target Governance Services<br>ConsentService, AuditService, MaskingPolicy,<br>EvidenceService, DisputeWorkflow", 1380, 430, 390, 170, STYLES["governance"])
    endpoints = page.vertex("API contract<br>/api/v1/graph<br>/businesses/{id}<br>/simulation/shock<br>/recommendations/suppliers<br>/invoices/{id}/verification", 1380, 700, 390, 180, STYLES["platform"])

    for cid in ui_ids:
        page.edge(cid, api, "fetch / props")
    page.edge(api, loader, "load_data")
    page.edge(loader, csv, "read")
    page.edge(api, risk, "calculate_business_risk")
    page.edge(api, matching, "rank_suppliers")
    page.edge(api, shock, "simulate_shock")
    page.edge(api, invoice, "optional verification")
    page.edge(gov, api, "cross-cutting gate", STYLES["dashed_edge"])
    page.edge(gov, endpoints, "masking + consent + audit")
    page.edge(endpoints, api, "implemented in main.py")
    page.edge(loader, risk, "financial rows + edges")
    page.edge(loader, matching, "businesses + products + edges")
    page.edge(loader, shock, "businesses + edges")
    page.edge(csv, invoice, "invoice rows")

    page.vertex(
        "Implementation note:<br>Backend currently has dataclasses and pure functions, not full Pydantic schemas or separate route modules.",
        80,
        1060,
        590,
        95,
        STYLES["note"],
    )


def build_supply_graph(mxfile: Element) -> None:
    page = Page(mxfile, "13 Supply Network Data Graph", 1900, 1300)
    page.title(
        "13 Supply Network Data Graph",
        "Directed edges show supply flow from source supplier to target buyer. Public/pilot views should mask identity and exact volume unless consented.",
    )
    page.legend(40, 116)

    m1 = page.vertex("Manufacturer<br>BIZ-002 Saigon NutriDrink", 130, 360, 230, 80, STYLES["actor"])
    m2 = page.vertex("Manufacturer<br>BIZ-003 Packaged Food", 130, 560, 230, 80, STYLES["actor"])
    d1 = page.vertex("Distributor<br>BIZ-005 Dai Tin<br>RiskSignal: red", 520, 455, 230, 90, STYLES["risk"])
    w1 = page.vertex("Wholesaler<br>masked alias W-014", 900, 340, 230, 80, STYLES["platform"])
    r1 = page.vertex("Retailer SME<br>masked alias R-021", 1280, 260, 230, 80, STYLES["platform"])
    r2 = page.vertex("Retailer SME<br>masked alias R-034", 1280, 455, 230, 80, STYLES["platform"])
    r3 = page.vertex("Retailer SME<br>masked alias R-047", 1280, 650, 230, 80, STYLES["platform"])
    fp = page.vertex("Financial partner<br>consented risk/invoice package only", 900, 800, 270, 90, STYLES["finance"])
    inv = page.vertex("InvoiceVerification<br>hash + funded status", 520, 800, 260, 90, STYLES["finance"])

    page.edge(m1, d1, "beverage / volume range")
    page.edge(m2, d1, "packaged food / volume range")
    page.edge(d1, w1, "source -> target")
    page.edge(w1, r1, "monthly_volume range")
    page.edge(d1, r2, "direct downstream")
    page.edge(w1, r3, "downstream")
    page.edge(r2, inv, "buyer/seller invoice")
    page.edge(inv, fp, "share only with consent")
    page.edge(d1, fp, "risk summary only", STYLES["dashed_edge"])

    page.vertex(
        "Edge attributes:<br>product, product_category, monthly_volume, lead_time_days, transport_cost, reliability, payment_term_days",
        130,
        950,
        520,
        110,
        STYLES["data"],
    )
    page.vertex(
        "Masking levels:<br>public_aggregate -> masked_business -> consented_match -> admin_audit",
        760,
        950,
        450,
        110,
        STYLES["governance"],
    )
    page.vertex(
        "Shock path:<br>distributor red signal can trigger scenario analysis and supplier shortlist, not an automatic commercial action.",
        1300,
        950,
        420,
        110,
        STYLES["note"],
    )


def build_rbac_graph(mxfile: Element) -> None:
    page = Page(mxfile, "14 RBAC & Data Visibility Graph", 1900, 1300)
    page.title(
        "14 RBAC & Data Visibility Graph",
        "Access is role + purpose + consent based. Every sensitive access produces an audit event.",
    )
    page.legend(40, 116)

    roles = [
        ("SME user", 80, 250),
        ("Supplier user", 80, 430),
        ("Financial partner", 80, 610),
        ("Admin / demo operator", 80, 790),
    ]
    role_ids = [page.vertex(label, x, y, 220, 70, STYLES["actor"]) for label, x, y in roles]
    policy = page.vertex("Access policy<br>role + purpose + consent + masking level", 440, 505, 290, 110, STYLES["governance"])
    audit = page.vertex("AuditLog<br>event, actor, subject, purpose, request_id", 440, 720, 290, 110, STYLES["governance"])
    views = [
        ("Own profile<br>own suppliers<br>own financial summary", 880, 230, STYLES["platform"]),
        ("Masked leads<br>accepted introductions<br>own products/capacity", 880, 410, STYLES["platform"]),
        ("Consented risk summary<br>invoice status<br>no raw graph by default", 880, 590, STYLES["finance"]),
        ("Synthetic full view<br>production export needs audit", 880, 770, STYLES["governance"]),
    ]
    view_ids = [page.vertex(label, x, y, 300, 90, style) for label, x, y, style in views]

    sensitive = page.vertex("Sensitive data classes<br>contacts, supplier/customer list, exact volume, financials, raw invoice", 1330, 395, 360, 140, STYLES["data"])
    consent = page.vertex("ConsentRecord<br>scope, purpose, expiry, revocation", 1330, 620, 360, 110, STYLES["governance"])
    dispute = page.vertex("Dispute / appeal<br>data correction and explanation review", 1330, 800, 360, 110, STYLES["governance"])

    for role_id in role_ids:
        page.edge(role_id, policy, "request")
    for view_id in view_ids:
        page.edge(policy, view_id, "allow/mask")
        page.edge(view_id, audit, "record")
    page.edge(policy, sensitive, "deny unless consented")
    page.edge(consent, policy, "grant / revoke")
    page.edge(audit, dispute, "evidence trail")
    page.edge(sensitive, consent, "requires")
    page.edge(dispute, policy, "correction may change access/signal")

    page.vertex(
        "Default API behavior:<br>`masked=true`; display_name differs from legal name; exact volume can be bucketed.",
        80,
        1010,
        550,
        100,
        STYLES["note"],
    )


def build_evidence_roadmap(mxfile: Element) -> None:
    page = Page(mxfile, "15 Evidence, Dispute & Roadmap Graph", 2000, 1400)
    page.title(
        "15 Evidence, Dispute & Roadmap Graph",
        "End-to-end accountability: every signal or recommendation can point back to evidence, version, consent and review status.",
    )
    page.legend(40, 116)

    source = page.vertex("Source documents<br>contracts, invoices, POS, ERP, logistics, certifications", 90, 300, 300, 120, STYLES["data"])
    lineage = page.vertex("Lineage record<br>source id, checksum, transform version", 480, 300, 300, 120, STYLES["governance"])
    evidence = page.vertex("EvidencePackage<br>source refs + calculation version + purpose", 870, 300, 320, 120, STYLES["governance"])
    outputs = page.vertex("Outputs<br>RiskSignal, SupplierShortlist, InvoiceVerificationSignal", 1280, 300, 330, 120, STYLES["risk"])
    review = page.vertex("Human review<br>approve next action, add context, request correction", 1280, 540, 330, 120, STYLES["governance"])
    dispute = page.vertex("DisputeCase<br>claim, evidence refs, resolution, audit trail", 870, 540, 320, 120, STYLES["governance"])
    audit = page.vertex("AuditLog<br>view, export, consent, intro, recalculation", 480, 540, 300, 120, STYLES["governance"])
    action = page.vertex("Allowed next action<br>monitor, request intro, RFQ/PO preview, partner referral", 1280, 780, 330, 120, STYLES["platform"])

    page.edge(source, lineage, "ingest")
    page.edge(lineage, evidence, "package")
    page.edge(evidence, outputs, "supports")
    page.edge(outputs, review, "requires context")
    page.edge(review, action, "human approved")
    page.edge(outputs, dispute, "appeal / correction")
    page.edge(dispute, evidence, "review refs")
    page.edge(evidence, audit, "record")
    page.edge(audit, dispute, "trace")

    phases = [
        ("MVP<br>synthetic data<br>rule-based functions<br>masked graph", 120, 1010, STYLES["platform"]),
        ("Pilot<br>consent records<br>supplier qualification<br>audit logs<br>backtesting", 520, 1010, STYLES["governance"]),
        ("Production<br>RBAC enforcement<br>Postgres/PostGIS<br>model registry<br>dispute workflow", 920, 1010, STYLES["governance"]),
        ("Finance ready<br>partner KYB/KYC<br>underwriting package<br>no platform credit approval", 1320, 1010, STYLES["finance"]),
    ]
    phase_ids = [page.vertex(label, x, y, 300, 150, style) for label, x, y, style in phases]
    for left, right in zip(phase_ids, phase_ids[1:]):
        page.edge(left, right, "maturity")
    page.vertex(
        "Definition of done for pilot:<br>consent table, audit log, masking default, evidence refs, dispute path, model validation notes.",
        120,
        1220,
        700,
        90,
        STYLES["note"],
    )


def build_mxfile() -> Element:
    mxfile = Element(
        "mxfile",
        {
            "host": "app.diagrams.net",
            "modified": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "agent": "Codex",
            "version": "24.7.17",
            "type": "device",
        },
    )
    build_system_context(mxfile)
    build_bounded_context(mxfile)
    build_activity_pages(mxfile)
    build_oop_class(mxfile)
    build_service_component(mxfile)
    build_supply_graph(mxfile)
    build_rbac_graph(mxfile)
    build_evidence_roadmap(mxfile)
    return mxfile


def write_pretty_xml(root: Element, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = tostring(root, encoding="utf-8")
    pretty = minidom.parseString(raw).toprettyxml(indent="  ", encoding="utf-8")
    path.write_bytes(pretty)


def main() -> None:
    write_pretty_xml(build_mxfile(), OUTPUT)
    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    main()
