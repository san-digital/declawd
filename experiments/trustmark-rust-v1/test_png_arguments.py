import unittest
from png_continuation import remove_arguments


class RemovalArguments(unittest.TestCase):
    def test_png_omits_jpeg_quality(self):
        args = remove_arguments("trustmark", "models", "input.png", "output.png")
        self.assertNotIn("--quality", args)
        self.assertEqual(args[-2:], ["--variant", "Q"])

    def test_other_formats_require_another_protocol(self):
        with self.assertRaisesRegex(ValueError, "PNG only"):
            remove_arguments("trustmark", "models", "input.jpg", "output.png")


if __name__ == "__main__":
    unittest.main()
