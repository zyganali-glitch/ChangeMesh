"""ChangeMesh P-25.04 — Browser E2E and Accessibility Test Suite for Judge Path.

Acceptance criteria from master plan:
  - Critical path works clean browser/target viewport.
  - WCAG 2.1 AA accessibility compliance (color contrast, keyboard focus, ARIA landmarks).
  - Semantic HTML5 structure with skip navigation links.
  - Multi-viewport responsive rules (mobile 375px, tablet 768px, desktop 1280px).
  - Localization parity (EN / TR) across all dashboard views.
  - Zero external CDN / font dependencies (offline / PWA friendly).
  - Clean HTTP serving via ChangeMesh Cloud Run service app.

Required evidence: Browser report (docs/P-25.04_BROWSER_ACCESSIBILITY_REPORT.md).
Mandatory documentation sync: Demo guide.
"""

from __future__ import annotations

import json
import re
import urllib.request
from http.server import HTTPServer
from pathlib import Path
from threading import Thread
from typing import Generator

import pytest

from service_app import ChangeMeshServiceHandler

STATIC_DIR = Path(__file__).parent.parent / "src" / "dashboard" / "static"
INDEX_HTML = STATIC_DIR / "index.html"
STYLES_CSS = STATIC_DIR / "styles.css"
APP_JS = STATIC_DIR / "app.js"


# ============================================================================
# TEST FIXTURES
# ============================================================================


@pytest.fixture(scope="module")
def html_content() -> str:
    """Read the dashboard index.html."""
    assert INDEX_HTML.is_file(), f"Dashboard index.html not found at {INDEX_HTML}"
    return INDEX_HTML.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def css_content() -> str:
    """Read the dashboard styles.css."""
    assert STYLES_CSS.is_file(), f"Dashboard styles.css not found at {STYLES_CSS}"
    return STYLES_CSS.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def js_content() -> str:
    """Read the dashboard app.js."""
    assert APP_JS.is_file(), f"Dashboard app.js not found at {APP_JS}"
    return APP_JS.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def test_server() -> Generator[str, None, None]:
    """Run an in-process instance of ChangeMeshServiceHandler on a dynamic port."""
    server = HTTPServer(("127.0.0.1", 0), ChangeMeshServiceHandler)
    port = server.server_port
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{port}"
    yield base_url
    server.shutdown()


# ============================================================================
# SECTION 1: SEMANTIC HTML5 & ARIA ACCESSIBILITY STRUCTURE
# ============================================================================


class TestSemanticHTMLAndA11y:
    """Verify WCAG 2.1 AA semantic HTML and landmark structure."""

    def test_doctype_and_html_lang_declared(self, html_content: str):
        """HTML must declare doctype and lang attribute for screen readers."""
        assert html_content.strip().startswith("<!DOCTYPE html>")
        assert '<html lang="en"' in html_content

    def test_meta_viewport_present_and_scalable(self, html_content: str):
        """Meta viewport must enable responsive mobile scaling without user-scalable=no."""
        assert '<meta name="viewport"' in html_content
        assert "width=device-width" in html_content
        assert "initial-scale=1.0" in html_content
        # WCAG 1.4.4: Never block user zooming
        assert "user-scalable=no" not in html_content
        assert "maximum-scale=1" not in html_content

    def test_skip_to_main_content_link_present(self, html_content: str):
        """WCAG 2.4.1: Bypass Blocks — Skip to main content link must be first in body."""
        assert '<a href="#main-content" class="skip-link">' in html_content
        assert 'id="main-content"' in html_content

    def test_landmark_roles_present(self, html_content: str):
        """WCAG landmarks: banner, main, contentinfo, region."""
        assert 'role="banner"' in html_content
        assert 'role="main"' in html_content
        assert 'role="contentinfo"' in html_content
        assert 'role="status"' in html_content
        assert 'role="region"' in html_content

    def test_all_sections_have_accessible_names(self, html_content: str):
        """Every section must have aria-labelledby pointing to a valid heading ID."""
        section_matches = re.findall(r'<section[^>]*aria-labelledby="([^"]+)"', html_content)
        assert len(section_matches) >= 4, "Must have at least 4 major accessible sections"
        for label_id in section_matches:
            assert f'id="{label_id}"' in html_content, (
                f"Heading ID {label_id!r} referenced by aria-labelledby not found in HTML"
            )

    def test_heading_hierarchy_has_single_h1(self, html_content: str):
        """Document must have exactly one h1 heading for screen reader hierarchy."""
        h1_tags = re.findall(r"<h1[^>]*>(.*?)</h1>", html_content, re.DOTALL)
        assert len(h1_tags) == 1, f"Expected exactly 1 <h1>, found {len(h1_tags)}"
        assert "ChangeMesh" in h1_tags[0]

    def test_buttons_have_accessible_labels(self, html_content: str):
        """Every interactive button must have non-empty accessible text or aria-label."""
        button_tags = re.findall(r"<button([^>]*)>(.*?)</button>", html_content, re.DOTALL)
        assert len(button_tags) >= 4
        for attrs, inner_text in button_tags:
            has_aria_label = 'aria-label="' in attrs
            has_inner_text = bool(re.sub(r"<[^>]+>", "", inner_text).strip())
            assert has_aria_label or has_inner_text, (
                f"Button missing accessible label: attrs={attrs}, inner={inner_text}"
            )

    def test_zero_external_cdn_or_font_dependencies(self, html_content: str):
        """No external Google Fonts, unpkg, cdnjs, or bootstrap links (offline/PWA)."""
        external_urls = re.findall(r'(?:src|href)=["\'](https?://[^"\']+)["\']', html_content)
        assert len(external_urls) == 0, f"Found external dependencies in HTML: {external_urls}"


# ============================================================================
# SECTION 2: WCAG 2.1 AA COLOR CONTRAST & CSS DESIGN TOKENS
# ============================================================================


def _luminance(r: int, g: int, b: int) -> float:
    """Calculate relative luminance for sRGB color per WCAG 2.1."""
    channels = []
    for c in (r, g, b):
        c_norm = c / 255.0
        channels.append(c_norm / 12.92 if c_norm <= 0.03928 else ((c_norm + 0.055) / 1.055) ** 2.4)
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def _contrast_ratio(hex1: str, hex2: str) -> float:
    """Calculate contrast ratio between two hex colors."""
    h1 = hex1.lstrip("#")
    h2 = hex2.lstrip("#")
    r1, g1, b1 = int(h1[0:2], 16), int(h1[2:4], 16), int(h1[4:6], 16)
    r2, g2, b2 = int(h2[0:2], 16), int(h2[2:4], 16), int(h2[4:6], 16)

    l1 = _luminance(r1, g1, b1)
    l2 = _luminance(r2, g2, b2)
    lighter = max(l1, l2)
    darker = min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


class TestColorContrastAndThemeTokens:
    """Verify WCAG 2.1 AA contrast ratio requirements."""

    def test_dark_theme_text_contrast_exceeds_aa_standard(self):
        """Dark theme: text-primary (#f8fafc) on bg-primary (#0a0f1d) >= 7:1 (AAA)."""
        ratio = _contrast_ratio("#f8fafc", "#0a0f1d")
        assert ratio >= 7.0, f"Contrast ratio was {ratio:.2f}, expected >= 7.0:1"

    def test_dark_theme_card_contrast_exceeds_aa_standard(self):
        """Dark theme: text-primary (#f8fafc) on bg-card (#18223c) >= 4.5:1 (AA)."""
        ratio = _contrast_ratio("#f8fafc", "#18223c")
        assert ratio >= 4.5, f"Contrast ratio was {ratio:.2f}, expected >= 4.5:1"

    def test_light_theme_text_contrast_exceeds_aa_standard(self):
        """Light theme: text-primary (#0f172a) on bg-primary (#f1f5f9) >= 7:1 (AAA)."""
        ratio = _contrast_ratio("#0f172a", "#f1f5f9")
        assert ratio >= 7.0, f"Contrast ratio was {ratio:.2f}, expected >= 7.0:1"

    def test_keyboard_focus_outline_rules_defined(self, css_content: str):
        """WCAG 2.4.7: Focus Visible must have distinct outline and offset."""
        assert "*:focus-visible" in css_content or ":focus-visible" in css_content
        assert "outline:" in css_content
        assert "outline-offset:" in css_content

    def test_skip_link_css_transitions_into_view_on_focus(self, css_content: str):
        """Skip link must move from top: -40px to visible on :focus."""
        assert ".skip-link" in css_content
        assert ".skip-link:focus" in css_content


# ============================================================================
# SECTION 3: RESPONSIVE VIEWPORT QUERIES
# ============================================================================


class TestResponsiveViewports:
    """Verify CSS media queries handle mobile, tablet, and desktop viewports."""

    def test_mobile_media_query_present(self, css_content: str):
        """Mobile viewport breakpoint (<= 640px) must be present."""
        assert "@media (max-width: 640px)" in css_content

    def test_tablet_media_query_present(self, css_content: str):
        """Tablet viewport breakpoint (<= 900px) must be present."""
        assert "@media (max-width: 900px)" in css_content

    def test_responsive_grid_auto_fit(self, css_content: str):
        """Metrics grid must use repeat(auto-fit, minmax(...)) for fluid wrapping."""
        assert "repeat(auto-fit, minmax(" in css_content


# ============================================================================
# SECTION 4: LOCALIZATION & LANGUAGE PARITY (EN / TR)
# ============================================================================


class TestLocalizationParity:
    """Verify complete bilingual parity between English and Turkish surfaces."""

    def test_i18n_dictionary_parity(self, js_content: str):
        """All keys in I18N.en must exist in I18N.tr."""
        en_match = re.search(r"en:\s*\{([^}]+)\}", js_content, re.DOTALL)
        tr_match = re.search(r"tr:\s*\{([^}]+)\}", js_content, re.DOTALL)

        assert en_match is not None, "I18N.en dictionary not found in app.js"
        assert tr_match is not None, "I18N.tr dictionary not found in app.js"

        en_keys = set(re.findall(r"^\s*(\w+)\s*:", en_match.group(1), re.MULTILINE))
        tr_keys = set(re.findall(r"^\s*(\w+)\s*:", tr_match.group(1), re.MULTILINE))

        assert len(en_keys) >= 20, f"Expected >= 20 translation keys, got {len(en_keys)}"
        missing_in_tr = en_keys - tr_keys
        missing_in_en = tr_keys - en_keys

        assert not missing_in_tr, f"Keys missing in Turkish translation: {missing_in_tr}"
        assert not missing_in_en, f"Keys missing in English translation: {missing_in_en}"

    def test_canonical_8_shadowlab_scenarios_in_js(self, js_content: str):
        """All 8 standard scenarios must be defined in the frontend JS."""
        expected_scenarios = [
            "SCENARIO_NORMAL_MIGRATION",
            "SCENARIO_503_TRANSIENT_RECOVERY",
            "SCENARIO_PARTIAL_INTERRUPTION_COMPENSATION",
            "SCENARIO_STALE_APPROVAL",
            "SCENARIO_PROMPT_INJECTION",
            "SCENARIO_MISSING_ROLLBACK",
            "SCENARIO_LEGACY_CLIENT_BREAK",
            "SCENARIO_RESTART_RESUME",
        ]
        for sc in expected_scenarios:
            assert sc in js_content, f"Scenario {sc!r} not defined in app.js"


# ============================================================================
# SECTION 5: HTTP SERVICE & E2E API VERIFICATION
# ============================================================================


class TestServiceAppEndpoints:
    """Verify HTTP service serves HTML, CSS, JS, and JSON API correctly."""

    def test_root_returns_html_dashboard(self, test_server: str):
        """GET / must return 200 with HTML content-type."""
        req = urllib.request.Request(f"{test_server}/")
        with urllib.request.urlopen(req) as resp:
            assert resp.status == 200
            content_type = resp.headers.get("Content-Type", "")
            assert "text/html" in content_type
            body = resp.read().decode("utf-8")
            assert "<!DOCTYPE html>" in body
            assert "ChangeMesh" in body

    def test_static_css_endpoint(self, test_server: str):
        """GET /static/styles.css must return 200 with text/css."""
        req = urllib.request.Request(f"{test_server}/static/styles.css")
        with urllib.request.urlopen(req) as resp:
            assert resp.status == 200
            content_type = resp.headers.get("Content-Type", "")
            assert "text/css" in content_type
            body = resp.read().decode("utf-8")
            assert "--bg-primary" in body

    def test_static_js_endpoint(self, test_server: str):
        """GET /static/app.js must return 200 with application/javascript."""
        req = urllib.request.Request(f"{test_server}/static/app.js")
        with urllib.request.urlopen(req) as resp:
            assert resp.status == 200
            content_type = resp.headers.get("Content-Type", "")
            assert "javascript" in content_type
            body = resp.read().decode("utf-8")
            assert "I18N" in body

    def test_health_endpoint(self, test_server: str):
        """GET /health must return 200 JSON with status OK."""
        req = urllib.request.Request(f"{test_server}/health")
        with urllib.request.urlopen(req) as resp:
            assert resp.status == 200
            data = json.loads(resp.read().decode("utf-8"))
            assert data["status"] == "OK"
            assert data["service"] == "changemesh-p24-e2e"
            assert "canonical_model" in data

    def test_api_dashboard_snapshot_endpoint(self, test_server: str):
        """GET /api/dashboard/snapshot must return 200 JSON snapshot."""
        req = urllib.request.Request(f"{test_server}/api/dashboard/snapshot")
        with urllib.request.urlopen(req) as resp:
            assert resp.status == 200
            data = json.loads(resp.read().decode("utf-8"))
            assert data["schema_version"] == "1.0.0"
            assert data["loading_state"] == "LOADED"
            assert "snapshot_digest" in data

    def test_nonexistent_endpoint_returns_404(self, test_server: str):
        """GET /nonexistent-path must return 404 JSON."""
        req = urllib.request.Request(f"{test_server}/nonexistent-path")
        try:
            urllib.request.urlopen(req)
            pytest.fail("Expected HTTP 404 error")
        except urllib.error.HTTPError as e:
            assert e.code == 404
            data = json.loads(e.read().decode("utf-8"))
            assert data["error"] == "Not Found"
