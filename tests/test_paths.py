import unittest

from termux_nas.paths import resolve


class ResolveTests(unittest.TestCase):
    def test_relative_and_absolute_virtual_paths(self):
        self.assertEqual(resolve("Photos", "2026/pic.jpg"), "Photos/2026/pic.jpg")
        self.assertEqual(resolve("Photos", "~/nas/Docs/a.txt"), "Docs/a.txt")

    def test_parent_stops_at_share_root(self):
        self.assertEqual(resolve("A/B", "../../../C"), "C")

    def test_rejects_other_absolute_paths(self):
        with self.assertRaises(ValueError):
            resolve("", "/etc/passwd")


if __name__ == "__main__":
    unittest.main()
