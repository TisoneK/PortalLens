"""The captive Wi-Fi portal analyzer.

Takes an :class:`AnalysisContext` (one or more captive-portal URLs,
optionally with HTML/HAR payloads), parses them passively, runs
fingerprint + relationship detection, and returns a :class:`PortalReport`
distinguishing observed facts, inferences, and hypotheses with explicit
confidence scores.

Active analysis (HTTP fetching, DNS lookups) is gated behind the
context's :class:`AcquisitionPolicy`. The default policy is passive —
the analyzer works purely from URLs and user-supplied payloads.
"""

from __future__ import annotations

from urllib.parse import urlparse

from portallens.evidence import Evidence, EvidenceType, Observation
from portallens.plugins.captive_wifi.fingerprints import FingerprintMatch, detect_fingerprints
from portallens.plugins.captive_wifi.relationship import infer_relationships
from portallens.plugins.captive_wifi.url_parser import (
    CaptivePortalFlavor,
    CaptivePortalURLHints,
    parse_captive_url,
)
from portallens.portal import (
    AnalysisContext,
    Portal,
    PortalFingerprint,
    PortalRelationship,
    PortalReport,
    PortalType,
)


class CaptiveWifiPortal(Portal):
    """Captive Wi-Fi portal analyzer.

    The analyzer is **passive by default**. It never fetches a URL, does
    DNS lookups, or probes TLS unless the caller passes an
    :class:`AcquisitionPolicy` enabling the relevant technique AND has
    authorization for the target.
    """

    portal_type = PortalType.CAPTIVE_WIFI

    def analyze(self, context: AnalysisContext) -> PortalReport:
        if not context.urls:
            raise ValueError("CaptiveWifiPortal requires at least one URL in the AnalysisContext")

        evidence: list[Evidence] = []
        observations: list[Observation] = []
        open_questions: list[str] = []

        # ------------------------------------------------------------------
        # 1. Capture evidence from every supplied URL.
        # ------------------------------------------------------------------
        # We pick the first URL that looks like a captive portal as the
        # primary. If none look captive, we use the first URL as
        # primary anyway — the user told us this is what they want
        # analyzed.
        primary_url = context.urls[0]
        primary_hints: CaptivePortalURLHints | None = None
        for url in context.urls:
            hints = parse_captive_url(url)
            if any(f != CaptivePortalFlavor.GENERIC for f in hints.flavors):
                primary_url = url
                primary_hints = hints
                break
        if primary_hints is None:
            primary_hints = parse_captive_url(primary_url)

        # Record evidence for the primary URL — host, path, key query params.
        evidence.extend(self._evidence_for_url(primary_hints))

        # Record host/path evidence for any other supplied URLs too —
        # they're the source of the local→external redirect inference.
        # `_evidence_for_url` handles redirect-evidence capture
        # internally (from link-login parameters); we don't duplicate
        # that here.
        for url in context.urls:
            if url == primary_url:
                continue
            hints = parse_captive_url(url)
            evidence.extend(self._evidence_for_url(hints, mark_external=True))

        # ------------------------------------------------------------------
        # 2. Run fingerprint detection — across ALL URLs, not just the
        # primary. The primary URL might be the local captive hostname
        # (e.g. maz.wifi) which only carries the MikroTik entry signature;
        # the ISPMan fingerprint lives on the OTHER URL (captive.ispman.tech).
        # We need to scan both to produce a complete picture.
        # ------------------------------------------------------------------
        fingerprint_matches = detect_fingerprints(primary_hints, evidence)
        # Run fingerprints for every other URL too, then merge. Dedupe
        # by (platform, version) — keep the highest-confidence match.
        seen_platforms: dict[tuple[str, str | None], FingerprintMatch] = {}
        for fp in fingerprint_matches:
            seen_platforms[(fp.platform, fp.version)] = fp
        for url in context.urls:
            if url == primary_url:
                continue
            url_hints = parse_captive_url(url)
            url_matches = detect_fingerprints(url_hints, evidence)
            for fp in url_matches:
                key = (fp.platform, fp.version)
                existing = seen_platforms.get(key)
                if existing is None or fp.confidence > existing.confidence:
                    seen_platforms[key] = fp
        fingerprint_matches = list(seen_platforms.values())
        fingerprint_matches.sort(key=lambda m: -m.confidence)

        # ------------------------------------------------------------------
        # 3. Run relationship inference.
        # ------------------------------------------------------------------
        relationships = infer_relationships(primary_hints, evidence, context.urls)

        # ------------------------------------------------------------------
        # 4. Build observations (facts, inferences, hypotheses).
        # ------------------------------------------------------------------
        observations.extend(self._fact_observations(primary_hints, evidence))
        observations.extend(self._inference_observations(primary_hints, fingerprint_matches, relationships))
        observations.extend(self._hypothesis_observations(primary_hints, relationships))

        # ------------------------------------------------------------------
        # 5. Open questions — gaps the evidence can't close.
        # ------------------------------------------------------------------
        open_questions.extend(self._open_questions(primary_hints, fingerprint_matches, relationships))

        return PortalReport(
            portal_type=self.portal_type,
            primary_url=primary_url,
            evidence=evidence,
            observations=observations,
            fingerprints=[
                PortalFingerprint(
                    platform=fp.platform,
                    version=fp.version,
                    confidence=fp.confidence,
                    evidence_ids=fp.evidence_ids,
                    note=fp.note,
                )
                for fp in fingerprint_matches
            ],
            relationships=relationships,
            open_questions=open_questions,
        )

    # ----------------------------------------------------------------------
    # Evidence capture
    # ----------------------------------------------------------------------

    def _evidence_for_url(
        self,
        hints: CaptivePortalURLHints,
        *,
        mark_external: bool = False,
    ) -> list[Evidence]:
        """Capture host, path, and key query-parameter evidence for a URL.

        ``mark_external`` is True for non-primary URLs — it doesn't
        change the evidence record, but the relationship analyzer uses
        it to know which hosts to treat as external redirect targets.
        """

        out: list[Evidence] = []
        source = hints.parsed.raw

        if hints.parsed.host:
            out.append(
                Evidence(
                    type=EvidenceType.URL_HOST,
                    source=source,
                    key="host",
                    value=hints.parsed.host,
                )
            )
        if hints.parsed.path and hints.parsed.path != "/":
            out.append(
                Evidence(
                    type=EvidenceType.URL_PATH,
                    source=source,
                    key="path",
                    value=hints.parsed.path,
                )
            )

        # Record every query parameter — they're all potential evidence.
        # The fingerprint detector picks the ones it cares about.
        # We redact potentially-sensitive values (canvasFingerprint,
        # cookie) to a short prefix — they're never useful in full in a
        # report.
        for key, value in hints.parsed.query_params:
            redacted = value
            if key in {"canvasFingerprint", "cookie", "userAgent"} and len(value) > 64:
                redacted = value[:64] + "…"
            out.append(
                Evidence(
                    type=EvidenceType.URL_PARAMETER,
                    source=source,
                    key=key,
                    value=redacted,
                )
            )

        # If MikroTik link-login points at an external host, record it
        # as redirect evidence. The link-login parameter on the external
        # portal URL points BACK at the hotspot's login page — so the
        # external portal's host is the redirect TARGET, and the
        # link-login value's host is the redirect SOURCE.
        if hints.mikrotik_link_login:
            source_host_in_param = (urlparse(hints.mikrotik_link_login).hostname or "").lower()
            own_host = hints.parsed.host.lower()
            if source_host_in_param and source_host_in_param != own_host:
                out.append(
                    Evidence(
                        type=EvidenceType.URL_REDIRECT,
                        source=source,
                        key="link_login_target",
                        value=hints.mikrotik_link_login,
                        note=(
                            f"link-login parameter on `{own_host}` points back at "
                            f"`{source_host_in_param}` — `{source_host_in_param}` "
                            f"redirects to `{own_host}`."
                        ),
                    )
                )
        # NOTE: We deliberately do NOT emit redirect evidence for
        # link-orig. The link-orig parameter is the URL the user was
        # originally trying to reach (e.g. Apple's captive probe
        # http://www.msftconnecttest.com/redirect), not a portal redirect.
        # Treating it as a portal redirect would produce false positives
        # like "msftconnecttest.com redirects to captive.ispman.tech".

        return out

    # ----------------------------------------------------------------------
    # Observation construction
    # ----------------------------------------------------------------------

    def _fact_observations(
        self,
        hints: CaptivePortalURLHints,
        evidence: list[Evidence],
    ) -> list[Observation]:
        """Observed facts — restatements of evidence with no inference."""

        out: list[Observation] = []
        source = hints.parsed.raw
        host_ev = next(
            (e for e in evidence if e.type is EvidenceType.URL_HOST and e.source == source),
            None,
        )
        if host_ev:
            out.append(
                Observation(
                    kind="fact",
                    statement=f"Primary portal hostname: `{hints.parsed.host}`",
                    confidence=100,
                    evidence_ids=[host_ev.id],
                )
            )

        from portallens.plugins.captive_wifi.url_parser import CaptivePortalFlavor

        if CaptivePortalFlavor.MIKROTIK in hints.flavors:
            mikrotik_evs = [
                e.id for e in evidence
                if e.type is EvidenceType.URL_PARAMETER
                and e.source == source
                and e.key in {"link-login", "link-orig", "link-login-only", "dst", "mac", "ip"}
            ]
            out.append(
                Observation(
                    kind="fact",
                    statement="URL carries the MikroTik RouterOS hotspot query-string signature (link-login / link-orig / dst / mac / ip).",
                    confidence=100,
                    evidence_ids=mikrotik_evs,
                )
            )
        if CaptivePortalFlavor.ISPMAN in hints.flavors:
            host_path_evs = [
                e.id for e in evidence
                if e.type in {EvidenceType.URL_HOST, EvidenceType.URL_PATH}
                and e.source == source
            ]
            out.append(
                Observation(
                    kind="fact",
                    statement="URL host + path match the ISPMan captive-portal scheme (captive.ispman.tech/hotspots/.../select).",
                    confidence=100,
                    evidence_ids=host_path_evs,
                )
            )

        # Record redirect facts — link-login / link-orig pointing at
        # an external host.
        redirect_evs = [e for e in evidence if e.type is EvidenceType.URL_REDIRECT]
        for ev in redirect_evs:
            target_host = (urlparse(ev.value).hostname or "").lower()
            if target_host:
                out.append(
                    Observation(
                        kind="fact",
                        statement=f"Portal on `{hints.parsed.host}` carries a redirect parameter pointing at `{target_host}`.",
                        confidence=100,
                        evidence_ids=[ev.id],
                    )
                )

        return out

    def _inference_observations(
        self,
        hints: CaptivePortalURLHints,
        fingerprints: list[FingerprintMatch],
        relationships: list[PortalRelationship],
    ) -> list[Observation]:
        """Inferences — conclusions drawn from evidence with confidence."""

        out: list[Observation] = []

        # Per-fingerprint inferences
        for fp in fingerprints:
            out.append(
                Observation(
                    kind="inference",
                    statement=f"Detected platform: **{fp.platform}** (confidence {fp.confidence}%).",
                    confidence=fp.confidence,
                    evidence_ids=fp.evidence_ids,
                    note=fp.note,
                )
            )

        # Per-relationship inferences — but only the high-confidence
        # ones get the "inference" label; speculative ones go in
        # _hypothesis_observations.
        for rel in relationships:
            if rel.confidence >= 40:
                out.append(
                    Observation(
                        kind="inference",
                        statement=f"Relationship `{rel.kind.value}`: {rel.other} (confidence {rel.confidence}%).",
                        confidence=rel.confidence,
                        evidence_ids=rel.evidence_ids,
                        note=rel.note,
                    )
                )

        return out

    def _hypothesis_observations(
        self,
        hints: CaptivePortalURLHints,
        relationships: list[PortalRelationship],
    ) -> list[Observation]:
        """Hypotheses — speculative explanations explicitly flagged for
        verification. Confidence is capped at 39 (low) by convention."""

        out: list[Observation] = []
        for rel in relationships:
            if rel.confidence < 40:
                out.append(
                    Observation(
                        kind="hypothesis",
                        statement=f"Hypothesis: {rel.other} (relationship kind: `{rel.kind.value}`).",
                        confidence=min(rel.confidence, 39),
                        evidence_ids=rel.evidence_ids,
                        note=(rel.note or "") + " Flagged as a hypothesis — verification required.",
                    )
                )
        return out

    def _open_questions(
        self,
        hints: CaptivePortalURLHints,
        fingerprints: list[FingerprintMatch],
        relationships: list[PortalRelationship],
    ) -> list[str]:
        """Open questions — gaps the evidence can't close."""

        questions: list[str] = []

        # Who operates the underlying Wi-Fi network?
        operates = [r for r in relationships if r.kind.value == "operates_network"]
        if operates:
            questions.append(
                f"Who is the legal / commercial entity behind `{operates[0].other}`? "
                "The URL identifies a local captive hostname, not an organization. "
                "Resolving this requires DNS records, TLS certificate inspection, or "
                "direct operator disclosure."
            )

        # Who is the upstream ISP?
        questions.append(
            "Who is the upstream Internet bandwidth provider? "
            "PortalLens cannot identify this from URL evidence alone — it requires "
            "IP/ASN ownership data, which is gated behind an authorized active "
            "assessment (DNS resolution + IP/ASN lookup)."
        )

        # Is Maz a reseller, or an operator using a 3rd-party platform?
        resells = [r for r in relationships if r.kind.value == "resells_bandwidth"]
        if resells:
            questions.append(
                "Is the local operator a bandwidth reseller, or an operator using "
                "ISPMan purely as a captive-portal platform? Resolving this requires "
                "package-pricing evidence, the operator's own commercial disclosure, "
                "or upstream ISP identification."
            )

        # MikroTik admin exposure?
        from portallens.plugins.captive_wifi.url_parser import CaptivePortalFlavor
        if CaptivePortalFlavor.MIKROTIK in hints.flavors:
            questions.append(
                "Is the MikroTik router's administrative interface exposed to the "
                "customer network? This is a common misconfiguration but cannot be "
                "determined from URL evidence — it requires an authorized active "
                "assessment (port scan + HTTP probe of likely admin paths)."
            )

        return questions
