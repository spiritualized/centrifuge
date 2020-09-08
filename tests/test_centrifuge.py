import os
import unittest
from unittest import mock
from unittest.mock import MagicMock

import argparse
import mockito

import centrifuge
from metafix.constants import ReleaseCategory


class TestCentrifuge(unittest.TestCase):

    def test_init(self):
        with mock.patch.object(centrifuge, "main", return_value=42):
            with mock.patch.object(centrifuge, "__name__", "__main__"):
                with mock.patch.object(centrifuge.sys, 'exit') as mock_exit:
                    centrifuge.init()
                    assert mock_exit.call_args[0][0] == 42

    def test_main(self):
        mockito.when(centrifuge).load_directory(mockito.ANY).thenReturn([], [])

        argparser = MagicMock(argparse.ArgumentParser)
        mockito.when(argparse).ArgumentParser().thenReturn(argparser)
        mockito.when(os.path).isdir(mockito.ANY).thenReturn(True)
        mockito.when(centrifuge).get_release_dirs_inner(mockito.ANY, mockito.ANY).thenReturn([])

        assert centrifuge.main() is None
        mockito.unstub()

    def test_guess_category_from_path(self):

        assert centrifuge.guess_category_from_path("path{0}to{0}Banging Tunes") is ReleaseCategory.ALBUM
        assert centrifuge.guess_category_from_path("{0}path{0}to{0}Banging Tunes [Mix]") is ReleaseCategory.MIX
        assert centrifuge.guess_category_from_path("path{0}to{0}Compilation{0}Banging Tunes".format(os.path.sep)) \
               is ReleaseCategory.COMPILATION
        assert centrifuge.guess_category_from_path("{0}path{0}to{0}Banging Tunes ep") is ReleaseCategory.EP