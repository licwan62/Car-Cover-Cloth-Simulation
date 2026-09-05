from __future__ import annotations

from pathlib import Path
import sys
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "blender"))

from seam_naming import (  # noqa: E402
    endpoint_marker_names,
    pair_seam_paths,
    parse_seam_name,
    validate_direction_markers,
)


class SeamNamingTests(unittest.TestCase):
    def test_parse_path_and_endpoint(self) -> None:
        path = parse_seam_name("S001_TOP")
        endpoint = parse_seam_name("S001_LEFT_A")
        self.assertEqual((path.seam_id, path.panel, path.endpoint), ("S001", "TOP", None))
        self.assertEqual(endpoint.endpoint, "A")

    def test_legacy_name_is_not_guessed(self) -> None:
        self.assertIsNone(parse_seam_name("SEAM_TOP_LEFT"))

    def test_pairs_are_derived_only_from_same_sewing_id(self) -> None:
        pairs = pair_seam_paths(
            ["S002_RIGHT", "S001_LEFT", "S001_TOP", "S002_TOP"]
        )
        self.assertEqual(pairs, [("S001_LEFT", "S001_TOP"), ("S002_RIGHT", "S002_TOP")])

    def test_ambiguous_pair_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "exactly two"):
            pair_seam_paths(["S001_TOP", "S001_LEFT", "S001_RIGHT"])

    def test_direction_markers_must_be_complete(self) -> None:
        names = {
            "S001_TOP",
            "S001_LEFT",
            "S001_TOP_A",
            "S001_TOP_B",
            "S001_LEFT_A",
        }
        self.assertEqual(
            validate_direction_markers(names),
            ["S001_LEFT missing direction markers: S001_LEFT_B"],
        )
        self.assertEqual(endpoint_marker_names("S001_TOP"), ("S001_TOP_A", "S001_TOP_B"))


if __name__ == "__main__":
    unittest.main()
