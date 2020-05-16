import logging
import os
import time
from collections import OrderedDict
from typing import List

import colored

import cleartag
from cleartag.Exceptions import ClearTagError
from exceptions import InvalidPathError
from metafix.Release import Release
from metafix.Track import Track
from metafix.functions import has_audio_extension


def load_directory(path_param: str):

    path = os.path.abspath(path_param)

    if not os.path.isdir(path):
        raise InvalidPathError("Not a folder: {0}".format(path))

    non_audio = []
    unreadable = []
    audio = OrderedDict()

    for file in list_files(path_param):
        if has_audio_extension(file):
            try:
                audio[file] = cleartag.read_tags(os.path.join(path_param, file))
                audio[file].__class__ = Track
            except ClearTagError as e:
                logging.getLogger(__name__).error(e)
                unreadable.append(file)
        else:
            non_audio.append(file)

    return audio, non_audio, unreadable


def list_files(parent_dir: str) -> List[str]:
    file_list = []
    list_files_inner(parent_dir, None, file_list)

    return file_list


def list_files_inner(parent, path, file_list) -> None:
    joined_path = os.path.join(parent, path) if path else parent
    for curr in os.scandir(joined_path):
        if curr.is_file():
            file_list.append(os.path.relpath(curr.path, parent))
        elif curr.is_dir():
            list_files_inner(parent, curr.path, file_list)


def rename_files(release: Release, parent_path: str, dry_run=False) -> None:

    renames = []

    # rename files
    for filename in release.tracks:
        correct_filename = release.tracks[filename].get_filename(release.is_va())

        if not correct_filename:
            return

        dest_path = os.path.join(parent_path, correct_filename)

        # if the track passes validation, and the filename differs from the calculated correct filename
        if filename != correct_filename and (
                # and the destination doesn't exist, or it's a case-insensitive match of the source
                not os.path.exists(dest_path) or os.path.normcase(filename) == os.path.normcase(correct_filename)):
            renames.append([filename, correct_filename])

    for rename in renames:
        if not dry_run:
            dest_path = os.path.join(parent_path, rename[1])

            if os.name == "nt" and len(dest_path) > 260:
                fn, ext = os.path.splitext(dest_path)
                dest_path = dest_path[0:260 - len(ext)] + ext

            if os.path.exists(dest_path) and os.path.normcase(rename[0]) != os.path.normcase(rename[1]):
                logging.getLogger(__name__).error("File already exists, could not rename: {0}".format(dest_path))
                continue

            while True:
                try:
                    os.rename(os.path.join(parent_path, rename[0]), dest_path)
                    break
                except PermissionError:
                    logging.getLogger(__name__).error("PermissionError: could not rename '{0}' -> '{1}', retrying..."
                                                      .format(os.path.join(parent_path, rename[0]), dest_path))
                    time.sleep(1)

            # clean up empty directories
            curr_parent_path = os.path.join(parent_path, os.path.split(rename[0])[0])
            while not os.listdir(curr_parent_path):
                os.rmdir(curr_parent_path)
                curr_parent_path = os.path.split(curr_parent_path)[0]

        release.tracks[rename[1]] = release.tracks.pop(rename[0])


def can_lock_path(path: str) -> bool:
    for curr in list_files(path):
        try:
            with open(os.path.join(path, curr), "rb+"):
                pass
        except PermissionError:
            return False
    return True


def color(str_in: str, color: str) -> str:
    return "{0}{1}{2}".format(color, str_in, colored.attr('reset'))
