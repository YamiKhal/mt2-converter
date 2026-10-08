import unittest

from mt2model.releases import newer_release, version_numbers


def release(tag: str, assets: list[str]) -> dict:
    return {
        "tag_name": tag,
        "html_url": f"https://github.com/YamiKhal/mt2-converter/releases/tag/{tag}",
        "body": "- Glowing costume faces\r\n",
        "assets": [{"name": name, "browser_download_url": f"https://example.invalid/{name}"} for name in assets],
    }


class ReleaseTests(unittest.TestCase):
    def test_versions_compare_by_number(self):
        self.assertEqual(version_numbers("v0.5.10"), (0, 5, 10))
        self.assertGreater(version_numbers("0.5.10"), version_numbers("0.5.9"))
        self.assertIsNone(version_numbers("latest"))

    def test_newer_release_offers_its_zip(self):
        found = newer_release(release("v0.5.9", ["notes.txt", "mt2_tools-0.5.9.zip"]), "0.5.8")
        self.assertEqual(found.version, "0.5.9")
        self.assertTrue(found.download.endswith("mt2_tools-0.5.9.zip"))
        self.assertEqual(found.notes, "- Glowing costume faces")

    def test_same_or_older_release_is_ignored(self):
        self.assertIsNone(newer_release(release("v0.5.8", ["mt2_tools-0.5.8.zip"]), "0.5.8"))
        self.assertIsNone(newer_release(release("v0.5.7", ["mt2_tools-0.5.7.zip"]), "0.5.8"))
        self.assertIsNone(newer_release({"tag_name": "nightly"}, "0.5.8"))

    def test_release_without_zip_still_links_its_page(self):
        found = newer_release(release("v0.6.0", []), "0.5.8")
        self.assertEqual(found.download, "")
        self.assertIn("v0.6.0", found.page)


if __name__ == "__main__":
    unittest.main()
