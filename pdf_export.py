"""
PDF export for Candidate-Market Fit Engine reports.

Generates a formatted, multi-section PDF from the output dict produced by output.py.
Uses reportlab Platypus for high-level layout.
"""
from __future__ import annotations

import io
from datetime import datetime
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    HRFlowable,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# --- Color palette ---
C_PRIMARY = colors.HexColor("#1B3A6B")      # dark navy
C_ACCENT = colors.HexColor("#2E86AB")       # blue
C_SUCCESS = colors.HexColor("#2D6A4F")      # green (strong fit)
C_WARNING = colors.HexColor("#E76F51")      # orange (competitive / gaps)
C_NEUTRAL = colors.HexColor("#6B7280")      # gray
C_LIGHT = colors.HexColor("#F3F4F6")        # light background for tables
C_WHITE = colors.white


def _styles():
    """Build style sheet."""
    base = getSampleStyleSheet()

    custom = {
        "Title": ParagraphStyle(
            "Title",
            fontSize=22,
            fontName="Helvetica-Bold",
            textColor=C_PRIMARY,
            spaceAfter=6,
            alignment=TA_CENTER,
        ),
        "Subtitle": ParagraphStyle(
            "Subtitle",
            fontSize=11,
            fontName="Helvetica",
            textColor=C_NEUTRAL,
            spaceAfter=4,
            alignment=TA_CENTER,
        ),
        "SectionHeader": ParagraphStyle(
            "SectionHeader",
            fontSize=14,
            fontName="Helvetica-Bold",
            textColor=C_PRIMARY,
            spaceBefore=16,
            spaceAfter=6,
            borderPad=4,
        ),
        "RoleHeader": ParagraphStyle(
            "RoleHeader",
            fontSize=12,
            fontName="Helvetica-Bold",
            textColor=C_ACCENT,
            spaceBefore=10,
            spaceAfter=4,
        ),
        "Body": ParagraphStyle(
            "Body",
            fontSize=10,
            fontName="Helvetica",
            textColor=colors.black,
            spaceAfter=4,
            leading=14,
        ),
        "BodySmall": ParagraphStyle(
            "BodySmall",
            fontSize=9,
            fontName="Helvetica",
            textColor=C_NEUTRAL,
            spaceAfter=3,
            leading=13,
        ),
        "Bold": ParagraphStyle(
            "Bold",
            fontSize=10,
            fontName="Helvetica-Bold",
            textColor=colors.black,
            spaceAfter=4,
        ),
        "Bullet": ParagraphStyle(
            "Bullet",
            fontSize=10,
            fontName="Helvetica",
            textColor=colors.black,
            leftIndent=14,
            spaceAfter=2,
            leading=13,
        ),
        "SuccessLabel": ParagraphStyle(
            "SuccessLabel",
            fontSize=10,
            fontName="Helvetica-Bold",
            textColor=C_SUCCESS,
        ),
        "WarningLabel": ParagraphStyle(
            "WarningLabel",
            fontSize=10,
            fontName="Helvetica-Bold",
            textColor=C_WARNING,
        ),
    }

    return {**{k: base[k] for k in base.byName if k in base.byName}, **custom}


def _divider(elements: list, color=C_ACCENT, width=0.5):
    elements.append(Spacer(1, 4))
    elements.append(HRFlowable(width="100%", thickness=width, color=color))
    elements.append(Spacer(1, 4))


def _fit_color(fit_band: str) -> colors.Color:
    return {
        "strong": C_SUCCESS,
        "competitive": C_ACCENT,
        "developmental": C_WARNING,
        "insufficient": colors.red,
    }.get(fit_band, C_NEUTRAL)


def _section_1(elements: list, snap: dict, styles: dict):
    if not snap.get("available"):
        return

    elements.append(Paragraph("1. Candidate Snapshot", styles["SectionHeader"]))
    _divider(elements)

    # Key metrics table
    years = snap.get("years_experience", 0)
    coherence = snap.get("narrative_coherence", "N/A")
    education = snap.get("highest_education", "N/A")
    primary = snap.get("primary_driver", "").replace("_", " ").title()
    secondary = snap.get("secondary_driver", "").replace("_", " ").title()

    metrics = [
        ["Years Experience", "Narrative Coherence", "Education"],
        [f"{years:.0f} years", coherence.title() if isinstance(coherence, str) else "N/A", education],
    ]
    tbl = Table(metrics, colWidths=[2.2 * inch, 2.2 * inch, 2.2 * inch])
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), C_PRIMARY),
        ("TEXTCOLOR", (0, 0), (-1, 0), C_WHITE),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("BACKGROUND", (0, 1), (-1, 1), C_LIGHT),
        ("FONTNAME", (0, 1), (-1, 1), "Helvetica"),
        ("FONTSIZE", (0, 1), (-1, 1), 10),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [C_LIGHT]),
        ("BOX", (0, 0), (-1, -1), 0.5, C_NEUTRAL),
        ("INNERGRID", (0, 0), (-1, -1), 0.3, C_NEUTRAL),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    elements.append(tbl)
    elements.append(Spacer(1, 8))

    # Narrative
    if snap.get("narrative_summary"):
        elements.append(Paragraph(snap["narrative_summary"], styles["Body"]))

    # Motivation
    if primary:
        elements.append(Spacer(1, 4))
        elements.append(Paragraph(
            f"<b>Primary Driver:</b> {primary}   |   <b>Secondary Driver:</b> {secondary}",
            styles["Body"]
        ))
    if snap.get("motivation_summary"):
        elements.append(Paragraph(f"<i>{snap['motivation_summary']}</i>", styles["BodySmall"]))

    # Industry signals
    signals = snap.get("industry_signals", [])
    if signals:
        elements.append(Spacer(1, 6))
        elements.append(Paragraph("<b>Industry Background:</b>", styles["Bold"]))
        for sig in signals:
            recency = sig.get("recency", "")
            industry = sig.get("industry", "")
            yrs = sig.get("years_approximate", 0)
            elements.append(Paragraph(
                f"- {industry} ({yrs:.0f} yrs, {recency}): {sig.get('evidence', '')}",
                styles["Bullet"]
            ))


def _section_2(elements: list, skills_section: dict, styles: dict):
    if not skills_section.get("available"):
        return

    elements.append(Paragraph("2. Skill Profile", styles["SectionHeader"]))
    _divider(elements)

    total = skills_section.get("total_skills", 0)
    onet = skills_section.get("onet_matched", 0)
    novel = skills_section.get("unmatched", 0)

    metrics = [
        ["Total Skills", "O*NET Matched", "Novel/Domain-Specific"],
        [str(total), str(onet), str(novel)],
    ]
    tbl = Table(metrics, colWidths=[2.2 * inch, 2.2 * inch, 2.2 * inch])
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), C_PRIMARY),
        ("TEXTCOLOR", (0, 0), (-1, 0), C_WHITE),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("BACKGROUND", (0, 1), (-1, 1), C_LIGHT),
        ("FONTNAME", (0, 1), (-1, 1), "Helvetica"),
        ("FONTSIZE", (0, 1), (-1, 1), 10),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOX", (0, 0), (-1, -1), 0.5, C_NEUTRAL),
        ("INNERGRID", (0, 0), (-1, -1), 0.3, C_NEUTRAL),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    elements.append(tbl)
    elements.append(Spacer(1, 8))

    # Skill clusters
    clusters = skills_section.get("clusters", [])
    if clusters:
        elements.append(Paragraph("<b>Skill Clusters:</b>", styles["Bold"]))
        for cluster in clusters:
            name = cluster.get("cluster_name", "")
            strength = cluster.get("strength", "")
            skills = ", ".join(cluster.get("skills", []))
            evidence = cluster.get("evidence_summary", "")
            elements.append(Paragraph(f"<b>{name}</b> — {strength}", styles["Body"]))
            if skills:
                elements.append(Paragraph(f"Skills: {skills}", styles["Bullet"]))
            if evidence:
                elements.append(Paragraph(f"Evidence: {evidence}", styles["BodySmall"]))
            elements.append(Spacer(1, 4))

    # Top skills table
    top = skills_section.get("top_skills", [])
    if top:
        elements.append(Paragraph("<b>Top Skills by Confidence:</b>", styles["Bold"]))
        rows = [["Skill", "Type", "Confidence"]]
        for s in top:
            rows.append([
                s.get("name", ""),
                s.get("type", "").replace("_", " ").title(),
                f"{s.get('confidence', 0):.0%}",
            ])
        tbl = Table(rows, colWidths=[3.0 * inch, 1.8 * inch, 1.0 * inch])
        tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), C_ACCENT),
            ("TEXTCOLOR", (0, 0), (-1, 0), C_WHITE),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [C_WHITE, C_LIGHT]),
            ("BOX", (0, 0), (-1, -1), 0.5, C_NEUTRAL),
            ("INNERGRID", (0, 0), (-1, -1), 0.3, C_NEUTRAL),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("ALIGN", (2, 0), (2, -1), "CENTER"),
        ]))
        elements.append(tbl)


def _section_3_4(elements: list, win_now: list, pivot: list, styles: dict):
    if win_now:
        elements.append(Paragraph("3. Win Now Roles", styles["SectionHeader"]))
        _divider(elements)
        elements.append(Paragraph("Roles where you can compete today.", styles["BodySmall"]))
        elements.append(Spacer(1, 4))

        for entry in win_now:
            fit = entry.get("fit", {})
            conf = entry.get("confidence") or {}
            role_name = fit.get("role_name", "Unknown")
            fit_band = fit.get("fit_band", "")
            composite = fit.get("composite_score", 0)
            structural = fit.get("structural_fit_score", 0)
            motivation = fit.get("motivation_alignment_score", 0)
            reasoning = fit.get("reasoning", "")
            confidence_band = conf.get("band", "N/A")

            fit_col = _fit_color(fit_band)
            elements.append(Paragraph(
                f"{role_name}",
                styles["RoleHeader"]
            ))

            # Scores row
            score_rows = [
                ["Overall Fit", "Structural Fit", "Motivation Alignment", "Confidence"],
                [
                    f"{composite:.0%} ({fit_band.title()})",
                    f"{structural:.0%}",
                    f"{motivation:.0%}",
                    confidence_band.title() if confidence_band != "N/A" else "N/A",
                ],
            ]
            tbl = Table(score_rows, colWidths=[1.65 * inch, 1.65 * inch, 1.65 * inch, 1.65 * inch])
            tbl.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), C_PRIMARY),
                ("TEXTCOLOR", (0, 0), (-1, 0), C_WHITE),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                ("BACKGROUND", (0, 1), (-1, 1), C_LIGHT),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("BOX", (0, 0), (-1, -1), 0.5, C_NEUTRAL),
                ("INNERGRID", (0, 0), (-1, -1), 0.3, C_NEUTRAL),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]))
            elements.append(tbl)

            if reasoning:
                elements.append(Spacer(1, 4))
                elements.append(Paragraph(reasoning, styles["Body"]))

            # Key gaps from this role's gap entry
            gap = entry.get("gap") or {}
            if gap.get("gaps"):
                elements.append(Paragraph("<b>Key Gaps:</b>", styles["Bold"]))
                for g in gap["gaps"][:3]:
                    desc = g.get("description", "")
                    addr = g.get("addressability", "")
                    elements.append(Paragraph(f"- {desc} ({addr})", styles["Bullet"]))
            elements.append(Spacer(1, 8))

    if pivot:
        sec_num = 4 if win_now else 3
        elements.append(Paragraph(f"{sec_num}. Invest to Pivot Roles", styles["SectionHeader"]))
        _divider(elements)
        elements.append(Paragraph("Roles worth investing in if you want to pivot.", styles["BodySmall"]))
        elements.append(Spacer(1, 4))

        for entry in pivot:
            fit = entry.get("fit", {})
            gap = entry.get("gap") or {}
            elements.append(Paragraph(fit.get("role_name", "Unknown"), styles["RoleHeader"]))
            elements.append(Paragraph(fit.get("reasoning", ""), styles["Body"]))
            if gap.get("pivot_rationale"):
                elements.append(Paragraph(f"<b>Pivot Rationale:</b> {gap['pivot_rationale']}", styles["Body"]))
            if gap.get("top_leverage_moves"):
                elements.append(Paragraph("<b>Highest-Leverage Moves:</b>", styles["Bold"]))
                for i, move in enumerate(gap["top_leverage_moves"], 1):
                    elements.append(Paragraph(f"{i}. {move}", styles["Bullet"]))
            elements.append(Spacer(1, 8))


def _section_5(elements: list, gaps: list, section_num: int, styles: dict):
    if not gaps:
        return

    elements.append(Paragraph(f"{section_num}. Detailed Gap Analysis", styles["SectionHeader"]))
    _divider(elements)

    for gap_result in gaps:
        role_name = gap_result.get("role_name", "Unknown")
        severity_band = gap_result.get("severity_band", "").title()
        composite_sev = gap_result.get("composite_severity", 0)
        pivot_viable = "Yes" if gap_result.get("pivot_viable") else "No"

        elements.append(Paragraph(
            f"{role_name} — {severity_band} severity ({composite_sev:.0%})",
            styles["RoleHeader"]
        ))
        elements.append(Paragraph(
            f"<b>Pivot Viable:</b> {pivot_viable}   |   "
            f"<b>Rationale:</b> {gap_result.get('pivot_rationale', '')}",
            styles["Body"]
        ))

        gap_items = gap_result.get("gaps", [])
        if gap_items:
            for g in gap_items:
                gap_type = g.get("gap_type", "").replace("_", " ").title()
                sev = g.get("severity", 0)
                addr = g.get("addressability", "")
                desc = g.get("description", "")
                move = g.get("leverage_move", "")
                elements.append(Paragraph(
                    f"- <b>{gap_type}</b> ({sev:.0%}, {addr}): {desc}",
                    styles["Bullet"]
                ))
                if move:
                    elements.append(Paragraph(f"  Action: {move}", styles["BodySmall"]))

        if gap_result.get("top_leverage_moves"):
            elements.append(Paragraph("<b>Top Leverage Moves:</b>", styles["Bold"]))
            for i, move in enumerate(gap_result["top_leverage_moves"], 1):
                elements.append(Paragraph(f"{i}. {move}", styles["Bullet"]))

        elements.append(Spacer(1, 8))


def _section_6(elements: list, strategic: dict, section_num: int, styles: dict):
    if not strategic:
        return

    elements.append(Paragraph(f"{section_num}. Strategic Recommendation", styles["SectionHeader"]))
    _divider(elements)

    rec = strategic.get("recommendation", "")
    summary = strategic.get("summary", "")

    if rec == "win_now":
        label = "WIN NOW"
        label_style = styles["SuccessLabel"]
    elif rec == "invest_to_pivot":
        label = "INVEST TO PIVOT"
        label_style = styles["WarningLabel"]
    elif rec == "dual_track":
        label = "DUAL TRACK"
        label_style = styles["SuccessLabel"]
    else:
        label = rec.upper().replace("_", " ")
        label_style = styles["Bold"]

    elements.append(Paragraph(label, label_style))
    elements.append(Spacer(1, 4))
    elements.append(Paragraph(summary, styles["Body"]))


def _section_7(elements: list, cross: dict, section_num: int, styles: dict):
    if not cross or not cross.get("role_ranking"):
        return

    elements.append(Paragraph(f"{section_num}. Cross-Role Analysis", styles["SectionHeader"]))
    _divider(elements)

    # Role comparison table
    rows = [["Role", "Fit", "Skill Coverage", "Effort to Fit"]]
    for r in cross.get("role_ranking", []):
        rows.append([
            r.get("role_name", ""),
            f"{r.get('composite_score', 0):.0%}",
            f"{r.get('overlap_score', 0):.0%}",
            f"{r.get('effort_to_fit', 0):.2f}",
        ])
    tbl = Table(rows, colWidths=[3.0 * inch, 1.2 * inch, 1.4 * inch, 1.2 * inch])
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), C_ACCENT),
        ("TEXTCOLOR", (0, 0), (-1, 0), C_WHITE),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [C_WHITE, C_LIGHT]),
        ("BOX", (0, 0), (-1, -1), 0.5, C_NEUTRAL),
        ("INNERGRID", (0, 0), (-1, -1), 0.3, C_NEUTRAL),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    elements.append(tbl)
    elements.append(Spacer(1, 8))

    # Leverage skills
    if cross.get("leverage_skills"):
        elements.append(Paragraph("<b>Highest-Leverage Skills to Develop:</b>", styles["Bold"]))
        for ls in cross["leverage_skills"]:
            roles_str = ", ".join(ls.get("roles_unlocked", []))
            elements.append(Paragraph(
                f"- <b>{ls['skill'].title()}</b> — unlocks: {roles_str}",
                styles["Bullet"]
            ))
            if ls.get("recommendation"):
                elements.append(Paragraph(f"  Action: {ls['recommendation']}", styles["BodySmall"]))

    # Shared gaps
    if cross.get("shared_gaps"):
        elements.append(Spacer(1, 6))
        elements.append(Paragraph("<b>Shared Gaps (Appear Across Multiple Roles):</b>", styles["Bold"]))
        for sg in cross["shared_gaps"]:
            roles_str = ", ".join(sg.get("roles_affected", []))
            elements.append(Paragraph(
                f"- <b>{sg['skill'].title()}</b> — affects {sg['leverage_multiplier']} roles "
                f"({roles_str}) | avg severity: {sg['avg_severity']:.0%} | {sg['addressability']}",
                styles["Bullet"]
            ))

    # Narrative
    if cross.get("comparative_narrative"):
        elements.append(Spacer(1, 6))
        elements.append(Paragraph(f"<b>Summary:</b> {cross['comparative_narrative']}", styles["Body"]))


def generate_pdf(output: dict[str, Any]) -> bytes:
    """Generate a PDF report from the output dict. Returns raw bytes."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=LETTER,
        rightMargin=0.75 * inch,
        leftMargin=0.75 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
    )

    styles = _styles()
    elements = []

    # --- Cover header ---
    elements.append(Paragraph("Candidate-Market Fit Report", styles["Title"]))
    generated = datetime.now().strftime("%B %d, %Y at %I:%M %p")
    elements.append(Paragraph(f"Generated {generated}", styles["Subtitle"]))
    elements.append(Paragraph(
        "Powered by the Babson AI Fellowship | Candidate-Market Fit Engine",
        styles["Subtitle"]
    ))
    _divider(elements, color=C_PRIMARY, width=1.5)
    elements.append(Spacer(1, 8))

    snap = output.get("section_1_snapshot", {})
    skills_section = output.get("section_2_skills", {})
    win_now = output.get("section_3_win_now", [])
    pivot = output.get("section_4_pivot", [])
    gaps = output.get("section_5_gaps", [])
    strategic = output.get("section_6_strategic", {})
    cross = output.get("section_7_cross_role", {})

    # Dynamic section numbering (mirrors app.py)
    next_sec = 3
    if not win_now and not pivot:
        next_sec = 3  # keeps numbering even if empty
    else:
        if win_now:
            next_sec = 4
        if pivot:
            next_sec = next_sec + 1

    _section_1(elements, snap, styles)
    elements.append(Spacer(1, 8))

    _section_2(elements, skills_section, styles)
    elements.append(Spacer(1, 8))

    _section_3_4(elements, win_now, pivot, styles)

    # Recalculate section number for gap analysis
    gap_sec = 3
    if win_now:
        gap_sec += 1
    if pivot:
        gap_sec += 1

    _section_5(elements, gaps, gap_sec, styles)

    strategic_sec = gap_sec + (1 if gaps else 0)
    _section_6(elements, strategic, strategic_sec, styles)

    cross_sec = strategic_sec + (1 if strategic else 0)
    _section_7(elements, cross, cross_sec, styles)

    doc.build(elements)
    return buf.getvalue()
