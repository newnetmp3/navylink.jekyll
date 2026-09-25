"""Offline regression coverage for the public MNP catalog scraper."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

import requests

from tools.sync_mnp_quicklinks import (
    canonical_url,
    extract_counts,
    fetch_catalog,
    parse_page,
)

SAMPLE = """
<html><body>
<div>Quick Link (436)</div><div>436 Results for</div>
<h3>MyNavy Assignment Quick Link</h3>
<p>https://mynavyassignment.dc3n.navy.mil/</p>
<p>Description:</p><p>Find available assignments.</p>
<p>Category: Assignment, Leave, Travel</p>
<h3>Navy COOL Quick Link</h3>
<p>https://www.cool.osd.mil/usn/</p>
<p>Description: Credentials and certifications.</p>
<p>Category: Training, Education, Qualifications</p>
</body></html>
"""


class SyncTests(unittest.TestCase):
    def test_parse_official_search_cards(self):
        links = parse_page(SAMPLE)
        self.assertEqual(len(links), 2)
        self.assertEqual(links[0]["name"], "MyNavy Assignment")
        self.assertEqual(links[0]["description"], "Find available assignments.")
        self.assertEqual(links[1]["url"], "https://www.cool.osd.mil/usn/")
        self.assertEqual(links[1]["mnp_categories"], "Training, Education, Qualifications")

    def test_expected_total(self):
        self.assertEqual(extract_counts(SAMPLE), (436, 436))

    def test_refuse_placeholders_and_bad_url_schemes(self):
        self.assertEqual(canonical_url("https://www.domain.com"), "")
        self.assertEqual(canonical_url("javascript:alert(1)"), "")
        self.assertEqual(canonical_url("https://www.cool.osd.mil/usn/?utm_source=mnp"), "https://www.cool.osd.mil/usn")

    def test_reject_blocked_github_runner_with_clear_error(self):
        response = requests.Response()
        response.status_code = 403
        response.url = "https://www.mn3p.navy.mil/web/guest/search"
        fake_session = Mock()
        fake_session.get.return_value = response
        with self.assertRaisesRegex(SystemExit, "HTTP 403"):
            fetch_catalog(fake_session)

    def test_html_export_fallback(self):
        with tempfile.TemporaryDirectory() as path:
            (Path(path) / "01.html").write_text(SAMPLE, encoding="utf-8")
            records, expected = fetch_catalog(Mock(), html_dir=Path(path))
            self.assertEqual(len(records), 2)
            self.assertEqual(expected, 436)


if __name__ == "__main__":
    unittest.main()
