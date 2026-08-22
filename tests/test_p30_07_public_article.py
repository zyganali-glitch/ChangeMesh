"""ChangeMesh P-30.07 — Public Build Article and Social Post Verification Suite.

Acceptance criteria from master plan:
  - Bonus content truthful/public/correctly tagged if pursued.
  - Verification that docs/P-30.07_PUBLIC_BUILD_ARTICLE_AND_SOCIAL_POST.md contains
    a technical deep-dive article and correctly tagged social announcements (X / LinkedIn).
  - Verification of required hashtags: #GeminiSprint, #GoogleCloud, #VertexAI, #ChangeMesh.

Required evidence: Published link or NOT_RUN (docs/P-30.07_PUBLIC_BUILD_ARTICLE_AND_SOCIAL_POST.md).
Mandatory documentation sync: Submission manifest.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
ARTICLE_PATH = REPO_ROOT / "docs" / "P-30.07_PUBLIC_BUILD_ARTICLE_AND_SOCIAL_POST.md"


class TestPublicBuildArticleAndSocialPosts:
    """Verify technical article content, social media copy, and required hackathon tags."""

    def test_article_file_exists_and_contains_article(self):
        """Article document must exist and have deep-dive technical sections."""
        assert ARTICLE_PATH.is_file(), f"Missing public article document: {ARTICLE_PATH}"
        text = ARTICLE_PATH.read_text(encoding="utf-8")

        assert "Building ChangeMesh: Rehearsing Breaking Enterprise Changes" in text
        assert "Gemini 3.6 Flash" in text
        assert "4-Lane Authority Model" in text
        assert "Zero-Custody VPC Boundary" in text

    def test_social_announcements_present(self):
        """Document must contain ready-to-publish social copy for X and LinkedIn."""
        text = ARTICLE_PATH.read_text(encoding="utf-8")

        assert "X / Twitter Post:" in text
        assert "LinkedIn Announcement:" in text
        assert "https://github.com/zyganali-glitch/ChangeMesh" in text

    def test_required_hackathon_hashtags(self):
        """Social announcements must include required event hashtags."""
        text = ARTICLE_PATH.read_text(encoding="utf-8")

        assert "#GeminiSprint" in text
        assert "#GoogleCloud" in text
        assert "#VertexAI" in text
        assert "#ChangeMesh" in text
