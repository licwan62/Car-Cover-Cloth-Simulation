from __future__ import annotations

from pathlib import Path
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class ProjectLayoutTests(unittest.TestCase):
    def test_required_directories_exist(self) -> None:
        required = (
            "config/cloth",
            "illustrator/export",
            "blender",
            "scripts/illustrator",
            "scripts/blender",
            "output/simulation",
            "output/reports",
            "output/debug",
            "tests/patterns",
            "tests/vehicles",
        )
        for relative_path in required:
            with self.subTest(path=relative_path):
                self.assertTrue((PROJECT_ROOT / relative_path).is_dir())

    def test_business_scripts_are_not_loose_in_project_root(self) -> None:
        self.assertEqual(list(PROJECT_ROOT.glob("*.py")), [])

    def test_required_entry_documents_exist(self) -> None:
        self.assertTrue((PROJECT_ROOT / "README.md").is_file())
        self.assertTrue((PROJECT_ROOT / "PROJECT_STARTUP.md").is_file())


if __name__ == "__main__":
    unittest.main()
