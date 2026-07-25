from __future__ import annotations

import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from PIL import Image

try:
    from photo_compress import photo_compress
except ImportError:  # 允许从工具目录直接运行测试
    import photo_compress


def task_for(source: Path, destination: Path, *, in_place: bool = False) -> photo_compress.CompressTask:
    return photo_compress.CompressTask(
        source_path=str(source),
        destination_path=str(destination),
        relative_path=source.name,
        image_format="JPEG",
        in_place=in_place,
        quality=70,
        optimize=True,
        progressive=True,
        png_compress_level=9,
        verify=True,
        settings_signature="test-signature",
    )


class CompressionTests(unittest.TestCase):
    def test_jpeg_output_preserves_dimensions_and_exif(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "source.jpg"
            destination = root / "output" / "source.jpg"
            image = Image.effect_noise((320, 240), 80).convert("RGB")
            exif = Image.Exif()
            exif[0x010F] = "Test Camera"
            image.save(source, format="JPEG", quality=100, exif=exif)

            result = photo_compress.compress_one(task_for(source, destination))

            self.assertEqual("compressed", result.status)
            self.assertLess(result.output_size, result.original_size)
            with Image.open(destination) as output:
                self.assertEqual((320, 240), output.size)
                self.assertEqual("Test Camera", output.getexif().get(0x010F))

    def test_invalid_image_does_not_create_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "broken.jpg"
            destination = root / "output.jpg"
            source.write_bytes(b"not a jpeg")

            result = photo_compress.compress_one(task_for(source, destination))

            self.assertEqual("failed", result.status)
            self.assertFalse(destination.exists())

    def test_rgba_png_preserves_alpha_channel(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "source.png"
            destination = root / "output" / "source.png"
            Image.new("RGBA", (64, 64), (255, 0, 0, 80)).save(source, compress_level=0)
            task = photo_compress.CompressTask(
                source_path=str(source),
                destination_path=str(destination),
                relative_path="source.png",
                image_format="PNG",
                in_place=False,
                quality=88,
                optimize=True,
                progressive=True,
                png_compress_level=9,
                verify=True,
                settings_signature="png-test",
            )

            result = photo_compress.compress_one(task)

            self.assertEqual("compressed", result.status)
            with Image.open(destination) as output:
                self.assertEqual("RGBA", output.mode)
                self.assertEqual(80, output.getpixel((0, 0))[3])


class StateTests(unittest.TestCase):
    def test_state_only_matches_unchanged_file_and_settings(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "photo.jpg"
            path.write_bytes(b"photo")
            file_stat = path.stat()
            state = {
                "photo.jpg": {
                    "output_size": file_stat.st_size,
                    "output_mtime_ns": file_stat.st_mtime_ns,
                    "settings_signature": "same",
                }
            }

            self.assertTrue(
                photo_compress.already_processed(path, "photo.jpg", "same", state)
            )
            self.assertFalse(
                photo_compress.already_processed(path, "photo.jpg", "changed", state)
            )


class ValidationTests(unittest.TestCase):
    def test_rejects_output_inside_input_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            input_directory = Path(temporary_directory) / "input"
            input_directory.mkdir()
            parser = photo_compress.build_parser()
            args = parser.parse_args(
                [str(input_directory), "--output", str(input_directory / "output")]
            )

            with self.assertRaisesRegex(ValueError, "不能位于输入目录内部"):
                photo_compress.validate_arguments(args)

    def test_dry_run_does_not_create_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            input_directory = root / "input"
            output_directory = root / "output"
            input_directory.mkdir()
            Image.new("RGB", (10, 10), "red").save(input_directory / "photo.jpg")
            output = io.StringIO()

            with redirect_stdout(output):
                return_code = photo_compress.main(
                    [str(input_directory), "--output", str(output_directory), "--dry-run"]
                )

            self.assertEqual(0, return_code)
            self.assertFalse(output_directory.exists())
            self.assertIn("未创建或修改文件", output.getvalue())


if __name__ == "__main__":
    unittest.main()
