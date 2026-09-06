from __future__ import annotations

import base64
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from batch_gps_copy import cli


# A valid 1x1 JPEG lets the integration tests run without Pillow.
MINIMAL_JPEG = base64.b64decode(
    "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAP//////////////////////////////////////////////////////////////////////////////////////"
    "2wBDAf//////////////////////////////////////////////////////////////////////////////////////"
    "wAARCAABAAEDASIAAhEBAxEB/8QAFQABAQAAAAAAAAAAAAAAAAAAAAf/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/9oADAMBAAIQAxAAAAF//8QAFBABAAAAAAAAAAAAAAAAAAAAAP/aAAgBAQABBQJ//8QAFBEBAAAAAAAAAAAAAAAAAAAAAP/aAAgBAwEBPwF//8QAFBEBAAAAAAAAAAAAAAAAAAAAAP/aAAgBAgEBPwF//8QAFBABAAAAAAAAAAAAAAAAAAAAAP/aAAgBAQAGPwJ//8QAFBABAAAAAAAAAAAAAAAAAAAAAP/aAAgBAQABPyF//9oADAMBAAIAAwAAABD/xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oACAEDAQE/EB//xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oACAECAQE/EB//xAAUEAEAAAAAAAAAAAAAAAAAAAAA/9oACAEBAAE/EB//2Q=="
)


def write_jpeg(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(MINIMAL_JPEG)


def set_gps(exiftool: str, path: Path, latitude: float, longitude: float) -> None:
    latitude_ref = "N" if latitude >= 0 else "S"
    longitude_ref = "E" if longitude >= 0 else "W"
    subprocess.run(
        [
            exiftool,
            f"-GPSLatitude={abs(latitude)}",
            f"-GPSLatitudeRef={latitude_ref}",
            f"-GPSLongitude={abs(longitude)}",
            f"-GPSLongitudeRef={longitude_ref}",
            "-overwrite_original",
            str(path),
        ],
        check=True,
        capture_output=True,
    )


@unittest.skipUnless(shutil.which("exiftool"), "需要安装 ExifTool")
class BatchCopyIntegrationTests(unittest.TestCase):
    def test_skips_existing_gps_by_default_and_force_overwrites_it(self) -> None:
        exiftool = shutil.which("exiftool")
        assert exiftool is not None
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            template = root / "target_photo.JPG"
            photos = root / "photos"
            blank = photos / "blank.jpg"
            existing = photos / "existing.JPG"
            nested = photos / "nested" / "other.jpeg"
            for path in (template, blank, existing, nested):
                write_jpeg(path)
            set_gps(exiftool, template, 31.2304, 121.4737)
            set_gps(exiftool, existing, 39.9042, 116.4074)

            self.assertEqual(0, cli.main([str(template), str(photos)]))
            blank_gps, _ = cli.read_gps(exiftool, blank)
            existing_gps, _ = cli.read_gps(exiftool, existing)
            nested_gps, _ = cli.read_gps(exiftool, nested)
            self.assertIsNotNone(blank_gps)
            self.assertIsNotNone(existing_gps)
            self.assertIsNotNone(nested_gps)
            self.assertAlmostEqual(31.2304, float(blank_gps["GPSLatitude"]), places=6)
            self.assertAlmostEqual(39.9042, float(existing_gps["GPSLatitude"]), places=6)
            self.assertAlmostEqual(31.2304, float(nested_gps["GPSLatitude"]), places=6)
            self.assertEqual("N", blank_gps["GPSLatitudeRef"])
            self.assertEqual("E", blank_gps["GPSLongitudeRef"])

            self.assertEqual(0, cli.main([str(template), str(photos), "-f"]))
            overwritten_gps, _ = cli.read_gps(exiftool, existing)
            self.assertIsNotNone(overwritten_gps)
            self.assertAlmostEqual(31.2304, float(overwritten_gps["GPSLatitude"]), places=6)

            backup_files = [
                path
                for path in (photos / cli.BACKUP_DIRECTORY_NAME).rglob("*")
                if path.is_file() and path.suffix.lower() in cli.IMAGE_SUFFIXES
            ]
            self.assertEqual(5, len(backup_files))

    def test_rejects_template_without_coordinates(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            template = root / "target_photo.JPG"
            photos = root / "photos"
            write_jpeg(template)
            photos.mkdir()

            with self.assertRaises(SystemExit) as raised:
                cli.main([str(template), str(photos)])

            self.assertEqual(2, raised.exception.code)


class DiscoveryTests(unittest.TestCase):
    def test_discovers_jpegs_recursively_and_excludes_template_and_backups(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            template = root / "template.jpg"
            write_jpeg(template)
            write_jpeg(root / "a.JPG")
            write_jpeg(root / "nested" / "b.jpeg")
            write_jpeg(root / cli.BACKUP_DIRECTORY_NAME / "old.jpg")
            (root / "notes.txt").write_text("not a photo", encoding="utf-8")

            found = list(cli.image_files(root, template))

            self.assertEqual(
                ["a.JPG", "nested/b.jpeg"],
                [path.relative_to(root).as_posix() for path in found],
            )


if __name__ == "__main__":
    unittest.main()
