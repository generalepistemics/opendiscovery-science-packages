from __future__ import annotations

import unittest
from unittest.mock import patch

import variant_resolution


class VariantResolutionTest(unittest.TestCase):
    @patch("variant_resolution.lookup_rsid")
    def test_rsid_resolution_queries_only_required_grch38_build(self, lookup) -> None:
        lookup.return_value = variant_resolution.Coord(chr="10", pos=112998590, ref="C", alts=["T"])

        result = variant_resolution.resolve_query_variant(
            input_type="rsid", input_value="rs7903146", target_build="GRCh38"
        )

        lookup.assert_called_once_with("rs7903146", "GRCh38")
        self.assertEqual(result["query_variant"]["canonical"], "10:112998590-C-T")
        self.assertIsNone(result["grch37"])
        self.assertEqual(result["rsid"], "rs7903146")

    @patch("variant_resolution.lookup_rsid")
    def test_rsid_resolution_queries_only_required_grch37_build(self, lookup) -> None:
        lookup.return_value = variant_resolution.Coord(chr="10", pos=114758349, ref="C", alts=["T"])

        result = variant_resolution.resolve_query_variant(
            input_type="rsid", input_value="rs7903146", target_build="GRCh37"
        )

        lookup.assert_called_once_with("rs7903146", "GRCh37")
        self.assertEqual(result["query_variant"]["canonical"], "10:114758349-C-T")
        self.assertIsNone(result["grch38"])

    @patch("variant_resolution.lookup_rsid")
    def test_native_coordinates_do_not_query_ensembl(self, lookup) -> None:
        result = variant_resolution.resolve_query_variant(
            input_type="grch38",
            input_value="10:112998590-C-T",
            target_build="GRCh38",
        )

        lookup.assert_not_called()
        self.assertEqual(result["query_variant"]["canonical"], "10:112998590-C-T")

    @patch("variant_resolution.lookup_rsid")
    def test_missing_target_mapping_preserves_dual_build_fallback(self, lookup) -> None:
        lookup.side_effect = [
            None,
            variant_resolution.Coord(chr="10", pos=112998590, ref="C", alts=["T"]),
            None,
        ]

        result = variant_resolution.resolve_query_variant(
            input_type="rsid", input_value="rs7903146", target_build="GRCh38"
        )

        self.assertEqual(lookup.call_count, 3)
        self.assertEqual(result["query_variant"]["canonical"], "10:112998590-C-T")

    @patch("variant_resolution.lookup_rsid")
    def test_invalid_rsid_does_not_query_ensembl(self, lookup) -> None:
        with self.assertRaisesRegex(ValueError, "rsid must start"):
            variant_resolution.resolve_query_variant(
                input_type="rsid", input_value="invalid", target_build="GRCh38"
            )

        lookup.assert_not_called()

    @patch("variant_resolution._get_json")
    def test_lookup_position_skips_rsid_with_different_alleles(self, get_json) -> None:
        get_json.return_value = [
            {"id": "rs-wrong", "alleles": ["A", "T"]},
            {"id": "rs-right", "alleles": ["A", "G"]},
        ]

        result = variant_resolution.lookup_position("1", 123, "GRCh37", "A", "G")

        self.assertEqual(result, ("rs-right", "A", ["G"]))

    @patch("variant_resolution._get_json")
    def test_lookup_position_rejects_coordinate_only_match(self, get_json) -> None:
        get_json.return_value = [{"id": "rs-wrong", "alleles": ["A", "T"]}]

        result = variant_resolution.lookup_position("1", 123, "GRCh37", "A", "G")

        self.assertIsNone(result)

    @patch("variant_resolution.resolve_position_both_builds")
    def test_coordinate_resolution_passes_input_alleles(self, resolve) -> None:
        resolve.return_value = None

        with self.assertRaises(variant_resolution.VariantResolutionError):
            variant_resolution.resolve_variant("grch37", "1:123:A:G")

        resolve.assert_called_once_with("1", 123, "GRCh37", "A", "G")


if __name__ == "__main__":
    unittest.main()
