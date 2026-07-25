from __future__ import annotations

import unittest
from decimal import Decimal

from focal_length_statistics import grouping


class StandardGroupingTests(unittest.TestCase):
    def test_nearby_normal_focal_lengths_map_to_50mm(self) -> None:
        for value in ("49", "50", "51"):
            with self.subTest(value=value):
                self.assertEqual(
                    Decimal("50"),
                    grouping.nearest_anchor(
                        Decimal(value),
                        grouping.DEFAULT_ANCHORS,
                    ),
                )

    def test_ratio_distance_is_symmetric(self) -> None:
        self.assertEqual(
            grouping.proportional_distance(Decimal("50"), Decimal("100")),
            grouping.proportional_distance(Decimal("100"), Decimal("50")),
        )

    def test_custom_anchors_are_sorted_and_deduplicated(self) -> None:
        self.assertEqual(
            (Decimal("24"), Decimal("35"), Decimal("50")),
            grouping.parse_anchors("50,24,35,50"),
        )

    def test_invalid_anchor_list_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "大于 0"):
            grouping.parse_anchors("24,0,50")


class ExactGroupingTests(unittest.TestCase):
    def test_bucket_rounding_uses_half_up(self) -> None:
        self.assertEqual(
            Decimal("36"),
            grouping.normalize_exact_focal_length(
                Decimal("35.5"),
                Decimal("1"),
            ),
        )
        self.assertEqual(
            Decimal("35.5"),
            grouping.normalize_exact_focal_length(
                Decimal("35.26"),
                Decimal("0.5"),
            ),
        )


if __name__ == "__main__":
    unittest.main()
