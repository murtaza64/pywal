"""Test imagemagick functions."""

import unittest

from pywal import palette


class TestGenColors(unittest.TestCase):
    """Test the gen_colors functions."""

    def test_gen_colors(self):
        """> Generate a colorscheme."""
        result = palette.get("tests/test_files/test.jpg")
        self.assertEqual(len(result["colors"]["color0"]), 7)

    def test_color_import(self):
        """> Read colors from a file."""
        result = palette.file("tests/test_files/test_file.json")
        self.assertEqual(result["colors"]["color0"], "#1F211E")

    def test_color_import_no_wallpaper(self):
        """> Read colors from a file without a wallpaper."""
        result = palette.file("tests/test_files/test_file2.json")
        self.assertEqual(result["wallpaper"], "None")

    def test_color_import_no_alpha(self):
        """> Read colors from a file without an alpha."""
        result = palette.file("tests/test_files/test_file2.json")
        self.assertEqual(result["alpha"], "100")

    def test_color_import_no_checkum(self):
        """> Read checksum from a file with no checksum"""
        result = palette.file("tests/test_files/test_file.json")
        self.assertEqual(result["checksum"], "None")

    def test_gen_colors_checksum(self):
        """> Generate a colorscheme with the wallpaper's checksum"""
        result = palette.get("tests/test_files/test.jpg")
        self.assertEqual(len(result["checksum"]), 32)


if __name__ == "__main__":
    unittest.main()
