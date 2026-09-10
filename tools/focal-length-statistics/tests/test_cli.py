from __future__ import annotations

import io
import tempfile
import unittest
from contextlib import redirect_stdout
from decimal import Decimal
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch

from focal_length_statistics import cli
from focal_length_statistics.grouping import DEFAULT_ANCHORS


class FileDiscoveryTests(unittest.TestCase):
    def test_recursively_finds_jpeg_extensions_case_insensitively(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "nested").mkdir()
            (root / "a.JPG").write_bytes(b"a")
            (root / "nested" / "b.jpeg").write_bytes(b"b")
            (root / "nested" / "ignored.png").write_bytes(b"c")

            files = list(cli.iter_jpeg_files(root))

            self.assertEqual(
                ["a.JPG", "nested/b.jpeg"],
                [path.relative_to(root).as_posix() for path in files],
            )

    def test_no_exif_condition_is_a_valid_empty_result(self) -> None:
        completed = CompletedProcess(
            args=["exiftool"],
            returncode=1,
            stdout="",
            stderr="1 files failed condition\n0 image files read",
        )
        with patch.object(cli.subprocess, "run", return_value=completed):
            records = cli.read_exif_records("exiftool", Path("photos"))
        self.assertEqual([], records)


class StatisticsTests(unittest.TestCase):
    def test_prefers_standard_equivalent_focal_length(self) -> None:
        record = {"FocalLengthIn35mmFormat": 35, "FocalLength35efl": 36}
        self.assertEqual(Decimal("35"), cli.extract_focal_length(record))

    def test_uses_composite_focal_length_as_fallback(self) -> None:
        record = {"FocalLength35efl": 26}
        self.assertEqual(Decimal("26"), cli.extract_focal_length(record))

    def test_sorts_by_count_then_focal_length(self) -> None:
        records = [
            *({"FocalLengthIn35mmFormat": 35} for _ in range(5)),
            *({"FocalLengthIn35mmFormat": 24} for _ in range(2)),
            *({"FocalLengthIn35mmFormat": 50} for _ in range(2)),
            {},
        ]

        statistics = cli.build_statistics(
            12,
            records,
            grouping_mode="exact",
            anchors=DEFAULT_ANCHORS,
            bucket_size=Decimal("1"),
        )

        self.assertEqual(10, statistics.exif_images)
        self.assertEqual(9, statistics.focal_length_images)
        self.assertEqual([35, 24, 50], [int(row.focal_length) for row in statistics.rows])
        self.assertAlmostEqual(50.0, statistics.rows[0].percentage)

    def test_standard_mode_aggregates_nearby_values(self) -> None:
        records = [
            {"FocalLengthIn35mmFormat": 49},
            {"FocalLengthIn35mmFormat": 50},
            {"FocalLengthIn35mmFormat": 51},
        ]

        statistics = cli.build_statistics(
            3,
            records,
            grouping_mode="standard",
            anchors=DEFAULT_ANCHORS,
            bucket_size=Decimal("1"),
        )

        self.assertEqual(1, len(statistics.rows))
        self.assertEqual(Decimal("50"), statistics.rows[0].focal_length)
        self.assertEqual(3, statistics.rows[0].count)

    def test_minimum_items_overrides_percentage_filter(self) -> None:
        rows = tuple(
            cli.FocalLengthRow(Decimal(value), count, percentage)
            for value, count, percentage in (
                (35, 50, 50.0),
                (24, 30, 30.0),
                (50, 10, 10.0),
                (85, 6, 6.0),
                (16, 2, 2.0),
                (70, 1, 1.0),
                (100, 1, 1.0),
            )
        )

        visible = cli.visible_rows(rows, minimum_percentage=5.0, minimum_items=5)

        self.assertEqual([35, 24, 50, 85, 16], [int(row.focal_length) for row in visible])

    def test_all_rows_above_threshold_are_visible(self) -> None:
        rows = tuple(
            cli.FocalLengthRow(Decimal(index), 10, 10.0) for index in range(1, 7)
        )
        self.assertEqual(6, len(cli.visible_rows(rows, 5.0, 5)))


class OutputTests(unittest.TestCase):
    def test_report_uses_exif_count_as_percentage_denominator(self) -> None:
        statistics = cli.Statistics(
            scanned_images=120,
            exif_images=100,
            focal_length_images=89,
            rows=(cli.FocalLengthRow(Decimal("35"), 50, 50.0),),
        )
        output = io.StringIO()

        with redirect_stdout(output):
            cli.print_report(
                statistics,
                minimum_percentage=5.0,
                minimum_items=5,
                grouping_mode="standard",
            )

        report = output.getvalue()
        self.assertIn("共有 100 张包含 EXIF", report)
        self.assertIn("35 mm：50 张", report)
        self.assertIn("50.00%", report)
        self.assertNotIn("×", report)


if __name__ == "__main__":
    unittest.main()
