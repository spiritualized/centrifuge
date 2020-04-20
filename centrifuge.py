import configparser
import logging
import os
import re
import shutil
import sys

import argparse
from collections import OrderedDict
from typing import List, Optional

import colored
from lastfmcache import LastfmCache

import cleartag
from functions import load_directory, rename_files, color, can_lock_path
from metafix.Release import Release
from metafix.ReleaseValidator import ReleaseValidator
from metafix.constants import ReleaseCategory
from metafix.functions import has_audio_extension, flatten_artists


def get_release_dirs(src_folder: str) -> List[str]:

    folders = []

    get_release_dirs_inner(src_folder, folders)

    return folders


def get_release_dirs_inner(folder: str, folders: List[str]) -> List[str]:

    files = []
    subdirs = []

    for curr in os.scandir(folder):
        if curr.is_file():
            files.append(curr.path)
        elif curr.is_dir():
            subdirs.append(curr.path)

    # no subfolders, media files present
    if (not subdirs and has_media_files(files)) or (subdirs and subdirs_are_discs(subdirs)):
        folders.append(folder)

    else:
        for subdir in subdirs:
            get_release_dirs_inner(subdir, folders)

    return folders


def has_media_files(files: List[str]) -> bool:
    result = False

    for file in files:
        if has_audio_extension(file):
            result = True

    return result


def subdirs_are_discs(subdirs: List[str]) -> bool:

    for curr in subdirs:
        folder_name = curr.split(os.path.sep)[-1]
        if re.findall(r'(disc|disk|cd) ?\d{1,2}', folder_name.lower()):
            files = [file.path for file in os.scandir(curr) if os.path.isfile(file)]
            if not has_media_files(files):
                return False
        else:
            return False

    return True


def validate_folder_name(release: Release, violations: List[str], folder_name: str, skip_comparison: bool,
                         group_by_category: bool = False) -> None:
    if not release.can_validate_folder_name():
        violations.append("Cannot validate folder name")
        return

    valid_folder_name = release.get_folder_name(group_by_category=group_by_category)
    if valid_folder_name != folder_name and not skip_comparison:
        violations.append("Invalid folder name - should be '{valid_folder_name}'"
                          .format(valid_folder_name=valid_folder_name))


def parse_args() -> argparse.Namespace:
    argparser = argparse.ArgumentParser()
    argparser.add_argument("mode", choices=['validate', 'fix', 'releases'])
    argparser.add_argument("path", help="root directory to scan for audio releases")
    argparser.add_argument('--show-violations', action='store_true',
                           help="print a detailed list of validation failures")
    argparser.add_argument('--dry-run', action='store_true', help="run without editing or moving any files")
    argparser.add_argument('--group-by-artist', action='store_true', help="group releases into artist folders")
    argparser.add_argument('--group-by-category', action='store_true', help="group releases into category folders")

    argparser_move = argparser.add_mutually_exclusive_group()

    argparser_move.add_argument("--move-fixed", action='store_true',
                                help="move validated releases into the root scan directory")
    argparser_move.add_argument("--move-fixed-to", help="move validated releases to another folder")

    argparser.add_argument('--only-move-valid', action='store_true', help="only move fully valid releases")

    return argparser.parse_args()


def print_list(list_to_print: List[str]) -> None:
    for v in list_to_print:
        print(v)
    if list_to_print:
        print()


def list_releases(release_dirs: List[str]) -> None:
    """List releases found in the scan directory"""

    print("Found release directories:")
    for curr in release_dirs:
        print(curr)
    print("Total: {0}".format(len(release_dirs)))


def format_violations_str(old_violations: List[str], fixed_violations: Optional[List[str]] = None) -> str:
    """Formats a colorized string of validation failures"""

    old_violations_str = color(str(len(old_violations)), colored.fg('red_1')) if len(old_violations) \
        else color(str(len(old_violations)), colored.fg('chartreuse_2a'))

    if fixed_violations is None:
        return old_violations_str

    if len(fixed_violations) == 0:
        violations_str = color(str(len(fixed_violations)), colored.fg('chartreuse_2a'))
    elif len(fixed_violations) == len(old_violations):
        violations_str = color(str(len(fixed_violations)), colored.fg('red_1'))
    else:
        violations_str = color(str(len(fixed_violations)), colored.fg('dark_orange'))

    return "{0} -> {1}".format(old_violations_str, violations_str)


def validate_releases(validator: ReleaseValidator, release_dirs: List[str], args: argparse.Namespace) -> None:
    """Validate releases found in the scan directory"""

    for curr_dir in release_dirs:
        audio, non_audio = load_directory(curr_dir)
        release = Release(audio)

        violations = validator.validate(release)
        validate_folder_name(release, violations, os.path.split(curr_dir)[1], False)

        print("{0} violations: {1}".format(format_violations_str(violations), curr_dir))

        if args.show_violations:
            print_list(violations)


def guess_category_from_path(path: str) -> Optional[ReleaseCategory]:
    """Extract a release category from a path. Defaults to Album if none can be inferred"""

    # check if up to 2 parent directories are an exact match of a category
    parent_dirs = path.split(os.path.sep)
    parent_dirs = parent_dirs[-3:-1] if len(parent_dirs) > 2 else parent_dirs
    parent_dirs.reverse()

    for category in ReleaseCategory:
        for curr_dir in parent_dirs:
            if curr_dir.lower() == category.value.lower():
                return category

    bracket_pairs = [["[", "]"], ["(", ")"], ["{", "}"]]
    release_dir = str(os.path.split(path)[1]).lower()

    # check if "[Category]" is contained in the release folder name
    for category in ReleaseCategory:
        for brackets in bracket_pairs:
            if "{0}{1}{2}".format(brackets[0], category.value.lower(), brackets[1]) in release_dir:
                return category

    # check if the release folder name ends with a space and a category name, without brackets (except Album)
    for category in [x for x in ReleaseCategory if x is not ReleaseCategory.ALBUM]:
        if release_dir.endswith(" {0}".format(category.value.lower())):
            return category

    # default to album
    return ReleaseCategory.ALBUM


def fix_releases(validator: ReleaseValidator, release_dirs: List[str], args: argparse.Namespace,
                 dest_folder: str) -> None:
    """Fix releases found in the scan directory"""

    for curr_dir in release_dirs:
        if not can_lock_path(curr_dir):
            logging.getLogger(__name__).error("Could not lock directory {0}".format(curr_dir))
            continue

        audio, non_audio = load_directory(curr_dir)

        release = Release(audio, guess_category_from_path(curr_dir))

        # fixed = None
        # while True:
        fixed = validator.fix(release)
        # break
        # except pylast.WSError as e:
        #     logging.getLogger(__name__).error("Failed to retrieve {0}".format(release))
        #     logging.getLogger(__name__).error(e)
        #     continue

        if not args.dry_run:
            for x in fixed.tracks:
                if fixed.tracks[x] != release.tracks[x]:
                    cleartag.write_tags(os.path.join(curr_dir, x), fixed.tracks[x])

        # rename files
        rename_files(fixed, curr_dir, args.dry_run)

        new_tracks = OrderedDict()
        for x in fixed.tracks:
            correct_filename = fixed.tracks[x].get_filename(fixed.is_va())
            if correct_filename:
                new_tracks[correct_filename] = fixed.tracks[x]
        fixed.tracks = new_tracks

        # calculate violations before and after fixing
        old_violations = validator.validate(release)
        validate_folder_name(release, old_violations, os.path.split(curr_dir)[1], False, args.group_by_category)
        violations = validator.validate(fixed)
        validate_folder_name(fixed, violations, os.path.split(curr_dir)[1], True)

        moved_dir = move_rename_folder(fixed, curr_dir, dest_folder, args)

        print("{0} violations: {1}".format(format_violations_str(old_violations, violations), moved_dir))

        if args.show_violations:
            print_list(old_violations)
            print_list(violations)


def move_rename_folder(release: Release, curr_dir: str, dest_folder: str, args: argparse.Namespace) -> str:
    """Rename a release folder, and move to a destination folder"""

    # if a dry run,or the folder name cannot be validated, do nothing
    if args.dry_run or not release.can_validate_folder_name():
        return curr_dir

    moved_dir = curr_dir

    # rename the release folder
    fixed_dir = os.path.join(os.path.split(curr_dir)[0],
                             release.get_folder_name(group_by_category=args.group_by_category))
    if curr_dir != fixed_dir:
        if not os.path.exists(fixed_dir) or os.path.normcase(curr_dir) == os.path.normcase(fixed_dir):
            os.rename(curr_dir, fixed_dir)
            moved_dir = fixed_dir
        else:
            logging.getLogger(__name__).error("Release folder already exists: {0}".format(fixed_dir))

    # move the release folder to a destination
    if dest_folder and (release.num_violations == 0 or args.only_move_valid is False):
        artist_folder = flatten_artists(release.validate_release_artists()) \
            if args.group_by_artist and not release.is_va() else ""

        category_folder = str(release.category.value) if args.group_by_category else ""
        curr_dest_parent_folder = os.path.join(dest_folder, category_folder, artist_folder)
        curr_dest_folder = os.path.join(curr_dest_parent_folder,
                                        release.get_folder_name(group_by_category=args.group_by_category))

        if fixed_dir != curr_dest_folder:
            if not os.path.exists(curr_dest_parent_folder):
                os.makedirs(curr_dest_parent_folder, exist_ok=True)
            if not os.path.exists(curr_dest_folder):
                os.rename(fixed_dir, curr_dest_folder)

                # clean up empty directories
                curr_src_parent_folder = os.path.split(fixed_dir)[0]
                while not os.listdir(curr_src_parent_folder):
                    os.rmdir(curr_src_parent_folder)
                    curr_src_parent_folder = os.path.split(curr_src_parent_folder)[0]
            else:
                logging.getLogger(__name__).error("Destination folder already exists: {0}".format(fixed_dir))

    return moved_dir


def main():

    args = parse_args()

    src_folder = os.path.abspath(args.path)
    if not os.path.isdir(src_folder):
        raise ValueError("Invalid source folder: {0}".format(src_folder))

    dest_folder = None
    if args.move_fixed:
        dest_folder = os.path.abspath(src_folder)
    elif args.move_fixed_to:
        dest_folder = os.path.abspath(args.move_fixed_to)
        if not os.path.isdir(dest_folder):
            raise ValueError("Invalid destination folder: {0}".format(dest_folder))

    release_dirs = get_release_dirs(src_folder)

    if args.mode == "releases":
        list_releases(release_dirs)

    elif args.mode in ["validate", "fix"]:
        lastfm_api_key, lastfm_shared_secret = load_lastfm_config()
        lastfm = LastfmCache(lastfm_api_key, lastfm_shared_secret)
        lastfm.enable_file_cache(86400*365*5)

        validator = ReleaseValidator(lastfm)

        if args.mode == "validate":
            validate_releases(validator, release_dirs, args)

        elif args.mode == "fix":
            fix_releases(validator, release_dirs, args, dest_folder)


def load_lastfm_config():
    root_dir = os.path.dirname(os.path.abspath(__file__))
    ini_filename = "lastfm.ini"

    if not os.path.isfile(os.path.join(root_dir, ini_filename)):
        shutil.copy(os.path.join(root_dir, "ini_template"), os.path.join(root_dir, ini_filename))

    config = configparser.ConfigParser()
    config.read(os.path.join(root_dir, "lastfm.ini"))

    if 'lastfm' not in config:
        raise ValueError("Invalid {0} config file".format(ini_filename))
    if not config['lastfm'].get('api_key') or not config['lastfm'].get('shared_secret'):
        logging.getLogger(__name__).error("Add your lastfm API key and shared secret into {0}".format(ini_filename))
        exit(1)

    return config['lastfm']['api_key'], config['lastfm']['shared_secret']


def init():
    if __name__ == "__main__":
        sys.exit(main())


init()
