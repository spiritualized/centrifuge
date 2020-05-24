import os
import unittest
from unittest import mock
from unittest.mock import MagicMock

import argparse
import mockito

import centrifuge_main
from metafix.constants import ReleaseCategory


class TestCentrifuge(unittest.TestCase):

    def test_init(self):
        with mock.patch.object(centrifuge_main, "main", return_value=42):
            with mock.patch.object(centrifuge_main, "__name__", "__main__"):
                with mock.patch.object(centrifuge_main.sys, 'exit') as mock_exit:
                    centrifuge_main.init()
                    assert mock_exit.call_args[0][0] == 42

    def test_main(self):
        mockito.when(centrifuge_main).load_directory(mockito.ANY).thenReturn([], [])

        argparser = MagicMock(argparse.ArgumentParser)
        mockito.when(argparse).ArgumentParser().thenReturn(argparser)
        mockito.when(os.path).isdir(mockito.ANY).thenReturn(True)
        mockito.when(centrifuge_main).get_release_dirs_inner(mockito.ANY, mockito.ANY).thenReturn([])

        assert centrifuge_main.main() is None
        mockito.unstub()

    def test_guess_category_from_path(self):

        assert centrifuge_main.guess_category_from_path("path{0}to{0}Banging Tunes") is ReleaseCategory.ALBUM
        assert centrifuge_main.guess_category_from_path("{0}path{0}to{0}Banging Tunes [Mix]") is ReleaseCategory.MIX
        assert centrifuge_main.guess_category_from_path("path{0}to{0}Compilation{0}Banging Tunes".format(os.path.sep)) \
               is ReleaseCategory.COMPILATION
        assert centrifuge_main.guess_category_from_path("{0}path{0}to{0}Banging Tunes ep") is ReleaseCategory.EP