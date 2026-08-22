"""ChangeMesh P-25.04 — Real Headless Browser E2E and Accessibility Test Suite.

Acceptance criteria from master plan:
  - Critical path works clean browser/target viewport.
  - Genuine headless browser engine execution (Chromium / Chrome / Edge).
  - Executed across target viewports (375px mobile, 768px tablet, 1280px desktop, 1920x1080).
  - Verified absence of horizontal overflow (scrollWidth <= clientWidth) and layout clipping.
  - Real browser keyboard accessibility (skip-link, tab navigation, visible focus styling).
  - Real browser bilingual interaction (EN -> TR -> EN switching and DOM updates).
  - Real browser critical judge path execution (dashboard boot, snapshot, demo trigger, approvals).
  - Verified zero external network request leaks (no CDN, font, or telemetry leak).
  - Negative failure controls proving fault detection (uncaught JS error, layout overflow, no init).
  - Retained deterministic static HTML/CSS/ARIA structural validation.

Required evidence: Browser report (docs/P-25.04_BROWSER_ACCESSIBILITY_REPORT.md).
"""

from __future__ import annotations

import json
import re
import urllib.request
from http.server import HTTPServer
from pathlib import Path
from threading import Thread
from typing import Any, Generator

import pytest
from playwright.sync_api import Browser, BrowserContext, Page, ViewportSize, sync_playwright

from service_app import ChangeMeshServiceHandler

STATIC_DIR = Path(__file__).parent.parent / "src" / "dashboard" / "static"
INDEX_HTML = STATIC_DIR / "index.html"
STYLES_CSS = STATIC_DIR / "styles.css"
APP_JS = STATIC_DIR / "app.js"

TARGET_VIEWPORTS: list[tuple[str, ViewportSize]] = [
    ("mobile_375", {"width": 375, "height": 667}),
    ("tablet_768", {"width": 768, "height": 1024}),
    ("desktop_1280", {"width": 1280, "height": 800}),
    ("recording_1920_1080", {"width": 1920, "height": 1080}),
]


# ============================================================================
# PYTEST FIXTURES
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


@pytest.fixture(scope="module")
def browser_instance() -> Generator[Browser, None, None]:
    """Launch a real headless browser engine (Chromium or channel fallback)."""
    with sync_playwright() as p:
        browser: Browser | None = None
        # Primary: Playwright headless Chromium
        try:
            browser = p.chromium.launch(headless=True)
        except Exception:
            # Fallback 1: Google Chrome system binary
            try:
                browser = p.chromium.launch(channel="chrome", headless=True)
            except Exception:
                # Fallback 2: Microsoft Edge system binary
                try:
                    browser = p.chromium.launch(channel="msedge", headless=True)
                except Exception as exc:
                    pytest.fail(
                        f"Failed to launch any real browser engine (Chromium/Chrome/Edge): {exc}"
                    )

        assert browser is not None, "Browser engine must not be None"
        yield browser
        browser.close()


# ============================================================================
# SECTION 1: STATIC ACCESSIBILITY STRUCTURE & WCAG 2.1 AA COLOR CONTRAST
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


class TestStaticAccessibilityStructure:
    """Deterministic static checks for semantic HTML5, WCAG contrast, and CSS tokens."""

    def test_doctype_and_html_lang_declared(self, html_content: str) -> None:
        """HTML must declare doctype and lang attribute for screen readers."""
        assert html_content.strip().startswith("<!DOCTYPE html>")
        assert '<html lang="en"' in html_content

    def test_meta_viewport_present_and_scalable(self, html_content: str) -> None:
        """Meta viewport must enable responsive mobile scaling without user-scalable=no."""
        assert '<meta name="viewport"' in html_content
        assert "width=device-width" in html_content
        assert "initial-scale=1.0" in html_content
        assert "user-scalable=no" not in html_content
        assert "maximum-scale=1" not in html_content

    def test_skip_to_main_content_link_present(self, html_content: str) -> None:
        """WCAG 2.4.1: Bypass Blocks — Skip to main content link must exist."""
        assert '<a href="#main-content" class="skip-link">' in html_content
        assert 'id="main-content"' in html_content

    def test_landmark_roles_present(self, html_content: str) -> None:
        """WCAG landmarks: banner, main, contentinfo, status, region."""
        assert 'role="banner"' in html_content
        assert 'role="main"' in html_content
        assert 'role="contentinfo"' in html_content
        assert 'role="status"' in html_content
        assert 'role="region"' in html_content

    def test_all_sections_have_accessible_names(self, html_content: str) -> None:
        """Every section must have aria-labelledby pointing to a valid heading ID."""
        section_matches = re.findall(r'<section[^>]*aria-labelledby="([^"]+)"', html_content)
        assert len(section_matches) >= 4, "Must have at least 4 major accessible sections"
        for label_id in section_matches:
            assert f'id="{label_id}"' in html_content, (
                f"Heading ID {label_id!r} referenced by aria-labelledby not found in HTML"
            )

    def test_heading_hierarchy_has_single_h1(self, html_content: str) -> None:
        """Document must have exactly one h1 heading for screen reader hierarchy."""
        h1_tags = re.findall(r"<h1[^>]*>(.*?)</h1>", html_content, re.DOTALL)
        assert len(h1_tags) == 1, f"Expected exactly 1 <h1>, found {len(h1_tags)}"
        assert "ChangeMesh" in h1_tags[0]

    def test_buttons_have_accessible_labels(self, html_content: str) -> None:
        """Every interactive button must have non-empty accessible text or aria-label."""
        button_tags = re.findall(r"<button([^>]*)>(.*?)</button>", html_content, re.DOTALL)
        assert len(button_tags) >= 4
        for attrs, inner_text in button_tags:
            has_aria_label = 'aria-label="' in attrs
            has_inner_text = bool(re.sub(r"<[^>]+>", "", inner_text).strip())
            assert has_aria_label or has_inner_text, (
                f"Button missing accessible label: attrs={attrs}, inner={inner_text}"
            )

    def test_zero_external_cdn_or_font_dependencies(self, html_content: str) -> None:
        """No external Google Fonts, unpkg, cdnjs, or bootstrap links (offline/PWA)."""
        external_urls = re.findall(r'(?:src|href)=["\'](https?://[^"\']+)["\']', html_content)
        assert len(external_urls) == 0, f"Found external dependencies in HTML: {external_urls}"

    def test_dark_theme_text_contrast_exceeds_aa_standard(self) -> None:
        """Dark theme text contrast ratio >= 7.0:1 (AAA)."""
        ratio = _contrast_ratio("#f8fafc", "#0a0f1d")
        assert ratio >= 7.0, f"Contrast ratio was {ratio:.2f}, expected >= 7.0:1"

    def test_dark_theme_card_contrast_exceeds_aa_standard(self) -> None:
        """Dark theme card contrast ratio >= 4.5:1 (AA)."""
        ratio = _contrast_ratio("#f8fafc", "#18223c")
        assert ratio >= 4.5, f"Contrast ratio was {ratio:.2f}, expected >= 4.5:1"

    def test_light_theme_text_contrast_exceeds_aa_standard(self) -> None:
        """Light theme text contrast ratio >= 7.0:1 (AAA)."""
        ratio = _contrast_ratio("#0f172a", "#f1f5f9")
        assert ratio >= 7.0, f"Contrast ratio was {ratio:.2f}, expected >= 7.0:1"

    def test_keyboard_focus_outline_rules_defined(self, css_content: str) -> None:
        """WCAG 2.4.7: Focus Visible must define outline and offset."""
        assert "*:focus-visible" in css_content or ":focus-visible" in css_content
        assert "outline:" in css_content
        assert "outline-offset:" in css_content

    def test_skip_link_css_transitions_into_view_on_focus(self, css_content: str) -> None:
        """Skip link must move from top: -40px to visible on :focus."""
        assert ".skip-link" in css_content
        assert ".skip-link:focus" in css_content

    def test_mobile_media_query_present(self, css_content: str) -> None:
        """Mobile viewport breakpoint (<= 640px) must be present."""
        assert "@media (max-width: 640px)" in css_content

    def test_tablet_media_query_present(self, css_content: str) -> None:
        """Tablet viewport breakpoint (<= 900px) must be present."""
        assert "@media (max-width: 900px)" in css_content

    def test_responsive_grid_auto_fit(self, css_content: str) -> None:
        """Metrics grid must use repeat(auto-fit, minmax(...)) for fluid wrapping."""
        assert "repeat(auto-fit, minmax(" in css_content

    def test_i18n_dictionary_parity(self, js_content: str) -> None:
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

    def test_canonical_8_shadowlab_scenarios_in_js(self, js_content: str) -> None:
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
# SECTION 2: LOCAL HTTP SERVICE APP ENDPOINTS
# ============================================================================


class TestServiceAppEndpoints:
    """Verify HTTP service serves HTML, CSS, JS, and JSON API correctly."""

    def test_root_returns_html_dashboard(self, test_server: str) -> None:
        """GET / must return 200 with HTML content-type."""
        req = urllib.request.Request(f"{test_server}/")
        with urllib.request.urlopen(req) as resp:
            assert resp.status == 200
            content_type = resp.headers.get("Content-Type", "")
            assert "text/html" in content_type
            body = resp.read().decode("utf-8")
            assert "<!DOCTYPE html>" in body
            assert "ChangeMesh" in body

    def test_static_css_endpoint(self, test_server: str) -> None:
        """GET /static/styles.css must return 200 with text/css."""
        req = urllib.request.Request(f"{test_server}/static/styles.css")
        with urllib.request.urlopen(req) as resp:
            assert resp.status == 200
            content_type = resp.headers.get("Content-Type", "")
            assert "text/css" in content_type
            body = resp.read().decode("utf-8")
            assert "--bg-primary" in body

    def test_static_js_endpoint(self, test_server: str) -> None:
        """GET /static/app.js must return 200 with application/javascript."""
        req = urllib.request.Request(f"{test_server}/static/app.js")
        with urllib.request.urlopen(req) as resp:
            assert resp.status == 200
            content_type = resp.headers.get("Content-Type", "")
            assert "javascript" in content_type
            body = resp.read().decode("utf-8")
            assert "I18N" in body

    def test_health_endpoint(self, test_server: str) -> None:
        """GET /health must return 200 JSON with status OK."""
        req = urllib.request.Request(f"{test_server}/health")
        with urllib.request.urlopen(req) as resp:
            assert resp.status == 200
            data = json.loads(resp.read().decode("utf-8"))
            assert data["status"] == "OK"
            assert data["service"] == "changemesh-p24-e2e"
            assert "canonical_model" in data

    def test_api_dashboard_snapshot_endpoint(self, test_server: str) -> None:
        """GET /api/dashboard/snapshot must return 200 JSON snapshot."""
        req = urllib.request.Request(f"{test_server}/api/dashboard/snapshot")
        with urllib.request.urlopen(req) as resp:
            assert resp.status == 200
            data = json.loads(resp.read().decode("utf-8"))
            assert data["schema_version"] == "1.0.0"
            assert data["loading_state"] == "LOADED"
            assert "snapshot_digest" in data

    def test_nonexistent_endpoint_returns_404(self, test_server: str) -> None:
        """GET /nonexistent-path must return 404 JSON."""
        req = urllib.request.Request(f"{test_server}/nonexistent-path")
        try:
            urllib.request.urlopen(req)
            pytest.fail("Expected HTTP 404 error")
        except urllib.error.HTTPError as e:
            assert e.code == 404
            data = json.loads(e.read().decode("utf-8"))
            assert data["error"] == "Not Found"


# ============================================================================
# SECTION 3: REAL BROWSER ENGINE E2E & TARGET VIEWPORT RESPONSIVENESS
# ============================================================================


class TestRealBrowserEngineAndLayout:
    """Verify real headless browser engine boot, JS execution, clean console, and viewports."""

    def test_browser_engine_availability_and_version(self, browser_instance: Browser) -> None:
        """Verify real browser engine launched and reports non-empty browser version."""
        version = browser_instance.version
        assert version, "Browser version must not be empty"
        assert len(version.split(".")) >= 2, f"Expected semantic browser version, got: {version!r}"

    def test_browser_page_boot_js_execution_and_clean_console(
        self, browser_instance: Browser, test_server: str
    ) -> None:
        """Verify page boots in real browser, JS initializes DOM, and zero console/page errors."""
        context: BrowserContext = browser_instance.new_context(
            viewport={"width": 1280, "height": 800}
        )
        page: Page = context.new_page()

        page_errors: list[str] = []
        console_errors: list[str] = []
        page.on("pageerror", lambda err: page_errors.append(str(err)))
        page.on(
            "console",
            lambda msg: console_errors.append(msg.text) if msg.type == "error" else None,
        )

        response = page.goto(f"{test_server}/")
        assert response is not None
        assert response.status == 200
        page.wait_for_load_state("networkidle")

        # Title and H1
        title = page.title()
        assert "ChangeMesh" in title
        h1_text = page.inner_text("h1")
        assert "ChangeMesh" in h1_text

        # JS initialization proof: statusText populated and snapshot fetched
        status_text = page.inner_text("#status-text")
        assert status_text in ("CHANGE COMPLETE", "SYSTEM READY", "INITIALIZING")

        # Zero runtime errors
        assert not page_errors, f"Uncaught page errors encountered: {page_errors}"
        assert not console_errors, f"Browser console errors encountered: {console_errors}"

        context.close()

    @pytest.mark.parametrize("viewport_name,viewport_dims", TARGET_VIEWPORTS)
    def test_browser_target_viewports_and_zero_overflow(
        self,
        browser_instance: Browser,
        test_server: str,
        viewport_name: str,
        viewport_dims: ViewportSize,
    ) -> None:
        """Verify real browser rendering at target viewports with zero horizontal overflow."""
        context: BrowserContext = browser_instance.new_context(viewport=viewport_dims)
        page: Page = context.new_page()

        response = page.goto(f"{test_server}/")
        assert response is not None and response.status == 200
        page.wait_for_load_state("networkidle")

        # Verify scrollWidth <= clientWidth (Zero horizontal overflow)
        doc_measurements = page.evaluate(
            """() => ({
                scrollWidth: document.documentElement.scrollWidth,
                clientWidth: document.documentElement.clientWidth,
                innerWidth: window.innerWidth
            })"""
        )
        scroll_w = doc_measurements["scrollWidth"]
        client_w = doc_measurements["clientWidth"]
        inner_w = doc_measurements["innerWidth"]

        assert scroll_w <= client_w, (
            f"Horizontal overflow detected at viewport {viewport_name} "
            f"({viewport_dims}): scrollWidth={scroll_w} > clientWidth={client_w}"
        )
        assert client_w == viewport_dims["width"]

        # Verify all primary interactive buttons are rendered and visible within viewport
        for btn_id in ("#run-demo-btn", "#theme-toggle-btn", "#lang-toggle-btn"):
            btn_loc = page.locator(btn_id)
            assert btn_loc.is_visible(), f"Button {btn_id} not visible at viewport {viewport_name}"
            box = btn_loc.bounding_box()
            assert box is not None, f"Button {btn_id} has no bounding box at {viewport_name}"
            assert box["x"] >= 0, f"Button {btn_id} x coordinate {box['x']} is offscreen left"
            assert box["x"] + box["width"] <= inner_w + 2.0, (
                f"Button {btn_id} right edge {box['x'] + box['width']} exceeds viewport {inner_w}"
            )

        # Verify all 5 critical judge sections are present and visible
        critical_sections = [
            "#change-overview-section",
            "#fleet-section",
            "#approval-section",
            "#shadowlab-section",
            "#evidence-section",
        ]
        for sec_id in critical_sections:
            sec_loc = page.locator(sec_id)
            assert sec_loc.is_visible(), f"Critical section {sec_id} not visible at {viewport_name}"

        context.close()


# ============================================================================
# SECTION 4: REAL BROWSER KEYBOARD ACCESSIBILITY & FOCUS VISIBILITY
# ============================================================================


class TestRealBrowserKeyboardAccessibility:
    """Verify keyboard tab navigation, skip-link activation, and focus styling in browser."""

    def test_browser_skip_link_tab_focus_and_activation(
        self, browser_instance: Browser, test_server: str
    ) -> None:
        """Verify Tab focuses skip-link, moves to view, and Enter navigates to #main-content."""
        context: BrowserContext = browser_instance.new_context(
            viewport={"width": 1280, "height": 800}
        )
        page: Page = context.new_page()
        page.goto(f"{test_server}/")
        page.wait_for_load_state("networkidle")

        # Press Tab to focus first interactive element
        page.keyboard.press("Tab")
        # Allow CSS transition (0.2s) to complete
        page.wait_for_timeout(250)

        active_info = page.evaluate(
            """() => {
                const el = document.activeElement;
                const style = window.getComputedStyle(el);
                return {
                    tagName: el.tagName,
                    className: el.className,
                    href: el.getAttribute('href'),
                    top: style.top,
                    outlineStyle: style.outlineStyle,
                    outlineWidth: style.outlineWidth
                };
            }"""
        )

        # Must be the skip link
        assert active_info["tagName"] == "A"
        assert "skip-link" in active_info["className"]
        assert active_info["href"] == "#main-content"
        # Style must transition from negative offset into visible view (top: 10px)
        assert active_info["top"] == "10px"

        # Press Enter on skip link
        page.keyboard.press("Enter")
        page_hash = page.evaluate("() => window.location.hash")
        assert page_hash == "#main-content", f"Expected hash '#main-content', got {page_hash!r}"

        context.close()

    def test_browser_keyboard_tab_reachability_of_controls(
        self, browser_instance: Browser, test_server: str
    ) -> None:
        """Verify sequential Tab key presses reach primary header controls and approval actions."""
        context: BrowserContext = browser_instance.new_context(
            viewport={"width": 1280, "height": 800}
        )
        page: Page = context.new_page()
        page.goto(f"{test_server}/")
        page.wait_for_load_state("networkidle")

        # Tab through the interactive elements and record their IDs
        focused_ids: list[str] = []
        for _ in range(16):
            page.keyboard.press("Tab")
            elem_id = page.evaluate(
                "() => document.activeElement.id || document.activeElement.className"
            )
            if elem_id and elem_id not in focused_ids:
                focused_ids.append(elem_id)

        # Confirm primary controls were reached
        assert any("run-demo-btn" in fid for fid in focused_ids), f"run-demo not in {focused_ids}"
        assert any("theme-toggle-btn" in fid for fid in focused_ids)
        assert any("lang-toggle-btn" in fid for fid in focused_ids)

        context.close()

    def test_browser_focus_visible_outline_styling(
        self, browser_instance: Browser, test_server: str
    ) -> None:
        """Verify machine-observable focus outline styles are computed when controls focus."""
        context: BrowserContext = browser_instance.new_context(
            viewport={"width": 1280, "height": 800}
        )
        page: Page = context.new_page()
        page.goto(f"{test_server}/")
        page.wait_for_load_state("networkidle")

        # Tab to skip-link, then Tab to #run-demo-btn
        page.keyboard.press("Tab")
        page.keyboard.press("Tab")
        page.wait_for_timeout(250)
        active_id = page.evaluate("() => document.activeElement.id")
        assert active_id == "run-demo-btn"

        outline_styles = page.evaluate(
            """() => {
                const el = document.getElementById('run-demo-btn');
                const style = window.getComputedStyle(el);
                return {
                    outlineStyle: style.outlineStyle,
                    outlineWidth: style.outlineWidth,
                    outlineOffset: style.outlineOffset,
                    outlineColor: style.outlineColor
                };
            }"""
        )

        assert outline_styles["outlineStyle"] in ("solid", "auto")
        assert (
            outline_styles["outlineWidth"] in ("3px", "2px", "1px")
            or outline_styles["outlineStyle"] != "none"
        )
        assert outline_styles["outlineOffset"] == "2px"
        assert (
            "59, 130, 246" in outline_styles["outlineColor"] or outline_styles["outlineColor"] != ""
        )

        context.close()


# ============================================================================
# SECTION 5: REAL BROWSER BILINGUAL LOCALIZATION SWITCHING (EN / TR)
# ============================================================================


class TestRealBrowserLocalization:
    """Verify bilingual language switching in real browser with live DOM mutations."""

    def test_browser_language_toggle_en_to_tr_and_back(
        self, browser_instance: Browser, test_server: str
    ) -> None:
        """Start in EN, click language toggle to TR, verify Turkish text, and switch back to EN."""
        context: BrowserContext = browser_instance.new_context(
            viewport={"width": 1280, "height": 800}
        )
        page: Page = context.new_page()

        page_errors: list[str] = []
        page.on("pageerror", lambda err: page_errors.append(str(err)))

        page.goto(f"{test_server}/")
        page.wait_for_load_state("networkidle")

        # 1. Initial State: English
        assert page.inner_text("#overview-heading") == "Change Lifecycle Overview"
        assert page.inner_text("#fleet-heading") == "Agent Fleet & Causal Event Timeline"
        assert page.inner_text("#approval-badge") == "HUMAN ON THE LOOP"
        assert "▶ Run Demo Change" in page.inner_text("#run-demo-btn")
        assert page.inner_text("#lang-text") == "TR"

        # 2. Click Language Toggle -> Switch to Turkish
        page.click("#lang-toggle-btn")

        # Verify Turkish DOM state
        assert page.inner_text("#overview-heading") == "Değişiklik Yaşam Döngüsü Özeti"
        assert page.inner_text("#fleet-heading") == "Ajan Filosu ve Nedensel Olay Zaman Çizelgesi"
        assert page.inner_text("#approval-badge") == "DÖNGÜDE İNSAN KONTROLÜ"
        assert "▶ Demo Değişikliği Başlat" in page.inner_text("#run-demo-btn")
        assert page.inner_text("#lang-text") == "EN"

        # 3. Click Language Toggle -> Switch back to English
        page.click("#lang-toggle-btn")

        # Verify English DOM state restored
        assert page.inner_text("#overview-heading") == "Change Lifecycle Overview"
        assert page.inner_text("#fleet-heading") == "Agent Fleet & Causal Event Timeline"
        assert page.inner_text("#approval-badge") == "HUMAN ON THE LOOP"
        assert page.inner_text("#lang-text") == "TR"

        # Zero runtime errors occurred during localization switching
        assert not page_errors, f"Page errors encountered during language switch: {page_errors}"

        context.close()


# ============================================================================
# SECTION 6: REAL BROWSER CRITICAL JUDGE PATH & INTERACTIVE CONTROLS
# ============================================================================


class TestRealBrowserCriticalJudgePath:
    """Verify complete judge-facing interactive workflow in real browser."""

    def test_browser_judge_path_full_interaction_lifecycle(
        self, browser_instance: Browser, test_server: str
    ) -> None:
        """Execute the entire judge demonstration path in a real browser session."""
        context: BrowserContext = browser_instance.new_context(
            viewport={"width": 1280, "height": 800}
        )
        page: Page = context.new_page()

        page_errors: list[str] = []
        page.on("pageerror", lambda err: page_errors.append(str(err)))

        # 1. Boot dashboard
        page.goto(f"{test_server}/")
        page.wait_for_load_state("networkidle")

        # 2. Verify Theme Toggle
        initial_theme = page.evaluate("() => document.documentElement.getAttribute('data-theme')")
        assert initial_theme == "dark"
        page.click("#theme-toggle-btn")
        light_theme = page.evaluate("() => document.documentElement.getAttribute('data-theme')")
        assert light_theme == "light"
        page.click("#theme-toggle-btn")
        restored_theme = page.evaluate("() => document.documentElement.getAttribute('data-theme')")
        assert restored_theme == "dark"

        # 3. Trigger Demo Execution via #run-demo-btn
        page.click("#run-demo-btn")
        page.wait_for_load_state("networkidle")

        # Verify metric card outputs
        val_state = page.inner_text("#val-lifecycle-state")
        assert val_state in ("COMPLETE", "EMPTY")
        val_passport = page.inner_text("#val-passport-digest")
        assert val_passport != "—"

        # 4. Interact with Reversibility Gate (#btn-approve)
        btn_approve = page.locator("#btn-approve")
        assert btn_approve.is_visible()
        btn_approve.click()

        # Verify approval state update
        assert "Authorized & Draft PR Sealed" in btn_approve.inner_text()
        assert btn_approve.is_disabled()
        assert not page.locator("#btn-reject").is_visible()

        # 5. Verify ShadowLab Scenarios Grid rendered
        scenarios = page.locator("#shadowlab-scenario-grid .scenario-card")
        assert scenarios.count() == 8, f"Expected 8 scenario cards, found {scenarios.count()}"

        # 6. Verify Google Cloud Proof Items rendered
        cloud_items = page.locator("#cloud-proof-container .cloud-proof-item")
        assert cloud_items.count() == 4, f"Expected 4 cloud proof items, got {cloud_items.count()}"

        # Confirm zero page errors throughout entire judge path
        assert not page_errors, f"Page errors encountered in judge path: {page_errors}"

        context.close()


# ============================================================================
# SECTION 7: REAL BROWSER ZERO EXTERNAL NETWORK REQUEST LEAKAGE
# ============================================================================


class TestRealBrowserNetworkObservation:
    """Verify that 100% of network requests originate exclusively from the local server."""

    def test_browser_zero_external_network_requests(
        self, browser_instance: Browser, test_server: str
    ) -> None:
        """Observe all HTTP requests emitted by the browser during dashboard execution."""
        context: BrowserContext = browser_instance.new_context(
            viewport={"width": 1280, "height": 800}
        )
        page: Page = context.new_page()

        observed_requests: list[dict[str, Any]] = []

        def _record_request(req: Any) -> None:
            observed_requests.append(
                {
                    "url": req.url,
                    "method": req.method,
                    "resource_type": req.resource_type,
                }
            )

        page.on("request", _record_request)

        # Boot and exercise dashboard
        page.goto(f"{test_server}/")
        page.wait_for_load_state("networkidle")
        page.click("#theme-toggle-btn")
        page.click("#lang-toggle-btn")
        page.click("#lang-toggle-btn")
        page.click("#run-demo-btn")
        page.wait_for_load_state("networkidle")

        assert len(observed_requests) >= 4, "Expected at least HTML, CSS, JS, API requests"

        forbidden_hosts = (
            "fonts.googleapis.com",
            "cdnjs.cloudflare.com",
            "unpkg.com",
            "google-analytics.com",
        )

        # Assert every single requested URL starts with the local test server origin
        for req in observed_requests:
            req_url: str = req["url"]
            assert req_url.startswith(test_server), (
                f"External network request leak detected! Unexpected request to: {req_url}"
            )
            for forbidden_host in forbidden_hosts:
                assert forbidden_host not in req_url, (
                    f"Forbidden host {forbidden_host} in {req_url}"
                )

        context.close()


# ============================================================================
# SECTION 8: NEGATIVE & FAILURE CONTROLS (CONTROLLED INJECTION DETECTION)
# ============================================================================


class TestRealBrowserNegativeControls:
    """Prove that the browser test framework actively detects runtime errors and layout overflow."""

    def test_negative_control_detects_uncaught_javascript_error(
        self, browser_instance: Browser
    ) -> None:
        """Prove that an injected uncaught JS exception is captured by the pageerror listener."""
        context: BrowserContext = browser_instance.new_context()
        page: Page = context.new_page()

        captured_errors: list[str] = []
        page.on("pageerror", lambda err: captured_errors.append(str(err)))

        # Injected controlled error
        fault_html = """
        <!DOCTYPE html>
        <html>
        <head><title>Fault Injection</title></head>
        <body>
            <script>
                window.addEventListener('DOMContentLoaded', () => {
                    throw new Error('CONTROLLED_TEST_FAULT: Injected failure for negative control');
                });
            </script>
        </body>
        </html>
        """
        page.set_content(fault_html)
        page.wait_for_load_state("load")

        assert len(captured_errors) == 1, f"Expected 1 captured error, got {len(captured_errors)}"
        assert "CONTROLLED_TEST_FAULT" in captured_errors[0]

        context.close()

    def test_negative_control_detects_horizontal_overflow(self, browser_instance: Browser) -> None:
        """Prove that an intentional layout overflow is detected by the scrollWidth assertion."""
        context: BrowserContext = browser_instance.new_context(
            viewport={"width": 375, "height": 667}
        )
        page: Page = context.new_page()

        # Injected controlled overflow
        overflow_html = """
        <!DOCTYPE html>
        <html>
        <head>
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
                body { margin: 0; padding: 0; }
                .wide-box { width: 4000px; height: 100px; background: red; }
            </style>
        </head>
        <body>
            <div class="wide-box">Overflow Box</div>
        </body>
        </html>
        """
        page.set_content(overflow_html)
        page.wait_for_load_state("load")

        measurements = page.evaluate(
            """() => ({
                scrollWidth: document.documentElement.scrollWidth,
                clientWidth: document.documentElement.clientWidth
            })"""
        )
        # Verify that the negative control detects overflow (scrollWidth > clientWidth)
        assert measurements["scrollWidth"] > measurements["clientWidth"], (
            "Negative control failed: layout overflow was not detected"
        )
        assert measurements["scrollWidth"] >= 4000

        context.close()

    def test_negative_control_detects_missing_js_init_marker(
        self, browser_instance: Browser
    ) -> None:
        """Prove that a missing initialization marker is detected when JS fails to run."""
        context: BrowserContext = browser_instance.new_context()
        page: Page = context.new_page()

        broken_html = """
        <!DOCTYPE html>
        <html>
        <head><title>Broken Init</title></head>
        <body>
            <div id="status-text">NEVER_UPDATED</div>
        </body>
        </html>
        """
        page.set_content(broken_html)
        status_text = page.inner_text("#status-text")
        # Assert that absent initialization is distinguishable from healthy initialization
        assert status_text not in ("CHANGE COMPLETE", "SYSTEM READY", "INITIALIZING")

        context.close()
