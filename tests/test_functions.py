import os
import unittest
from unittest.mock import MagicMock

import mockito

import cleartag
import functions
from exceptions import InvalidPathError
from functions import load_directory, list_files
from metafix.Track import Track
from metafix.functions import tag_filter


class TestFunctions(unittest.TestCase):

    def test_load_directory(self):
        mockito.when(os.path).isdir(mockito.ANY).thenReturn(True)
        mockito.when(functions).list_files(mockito.ANY).thenReturn(["test.mp3", "test.txt"])
        mockito.when(cleartag).read_tags(mockito.ANY).thenReturn(Track())

        audio, non_audio = load_directory("placeholder/path")

        assert len(audio) == 1
        assert len(non_audio) == 1

        mockito.unstub()


    def test_load_directory_invalid(self):
        self.assertRaises(InvalidPathError, load_directory, "placeholder/path")


    def test_listFiles(self):
        fake_file = MagicMock(os.DirEntry)
        fake_file.path = "file.mp3"
        mockito.when(fake_file).is_file().thenReturn(True)

        fake_dir = MagicMock(os.DirEntry)
        fake_dir.path = "subdirectory"
        mockito.when(fake_dir).is_file().thenReturn(False)

        mockito.when(os).scandir("placeholder").thenReturn([fake_dir, fake_file])
        mockito.when(os).scandir(os.path.join("placeholder", "subdirectory")).thenReturn([])

        test = list_files("placeholder")
        assert "file.mp3" in test[0]

        mockito.unstub()

    def test_tag_filter(self):

        assert tag_filter("electronica", [], True) == "Electronica"
        assert tag_filter("electronica", [], False) == "electronica"
        assert tag_filter("uk", [], True) == "UK"

        assert tag_filter("a bad tag", ["bad"], True) is None
        assert tag_filter("1990", [], True) is None
        assert tag_filter("seen live", [], True) is None
        assert tag_filter("really cool album", [], True) is None