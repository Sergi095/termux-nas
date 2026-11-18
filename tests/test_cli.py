import unittest

from termux_nas.cli import parser


class MountModeTests(unittest.TestCase):
    def test_remote_range_io_is_default(self):
        self.assertTrue(parser().parse_args(["mount", "home"]).range_io)

    def test_cached_mode_is_explicit(self):
        self.assertFalse(parser().parse_args(["mount", "home", "--cached"]).range_io)

    def test_range_io_flag_remains_accepted(self):
        self.assertTrue(parser().parse_args(["mount", "home", "--range-io"]).range_io)


if __name__ == "__main__":
    unittest.main()
