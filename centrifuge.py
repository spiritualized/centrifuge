from __future__ import annotations
import configparser
import logging
import os
import re
import shutil
import sys

import argparse
import time
from collections import OrderedDict
from typing import List, Optional, Set, Tuple, Iterator

import colored

from lastfmcache import LastfmCache

import cleartag
from functions import load_directory, rename_files, color, can_lock_path
from metafix.Release import Release
from metafix.ReleaseValidator import ReleaseValidator
from metafix.Violation import Violation
from metafix.constants import ReleaseCategory, ViolationType, ReleaseSource
from metafix.functions import flatten_artists
from release_dir_scanner import get_release_dirs


class UniqueRelease:
    def __init__(self, artists: List[str], year: str, title: str, codec: str, rank: int, path: str):
        self.artists = artists
        self.year = year
        self.title = title
        self.codec = codec
        self.rank = rank
        self.path = path

    def __eq__(self, other):
        if not isinstance(other, UniqueRelease):
            return False

        return self.artists == other.artists and self.year == other.year and self.title == other.title \
               and self.codec == other.codec

    def __hash__(self):
        return hash((tuple(self.artists), self.year, self.title, self.codec))

    def __lt__(self, other: UniqueRelease) -> bool:
        return self.rank < other.rank

    def __gt__(self, other: UniqueRelease) -> bool:
        return self.rank > other.rank


def validate_folder_name(release: Release, violations: List[Violation], folder_name: str, skip_comparison: bool,
                         group_by_category: bool = False, codec_short: bool = True) -> None:
    if not release.can_validate_folder_name():
        violations.append(Violation(ViolationType.FOLDER_NAME, "Cannot validate folder name"))
        return

    valid_folder_name = release.get_folder_name(codec_short=codec_short, group_by_category=group_by_category)
    if valid_folder_name != folder_name and not skip_comparison:
        violations.append(Violation(ViolationType.FOLDER_NAME,
                                    "Invalid folder name '{folder_name}' should be '{valid_folder_name}'"
                                    .format(folder_name=folder_name, valid_folder_name=valid_folder_name)))


def add_unreadable_files(violations: List[Violation], unreadable: List[str]):
    for file in unreadable:
        violations.append(Violation(ViolationType.UNREADABLE, "Unreadable file: {0}".format(file)))


def parse_args() -> argparse.Namespace:
    argparser = argparse.ArgumentParser()
    argparser.add_argument("mode", choices=['validate', 'fix', 'releases'])
    argparser.add_argument("path", help="root directory to scan for audio releases")
    argparser.add_argument('--show-violations', action='store_true',
                           help="print a detailed list of validation failures")
    argparser.add_argument('--dry-run', action='store_true', help="run without editing or moving any files")
    argparser.add_argument('--group-by-artist', action='store_true', help="group releases into artist folders")
    argparser.add_argument('--group-by-category', action='store_true', help="group releases into category folders")
    argparser.add_argument('--full-codec-names', action='store_true',
                           help="always include the codec in the release folder name")

    argparser_move = argparser.add_mutually_exclusive_group()

    argparser_move.add_argument("--move-fixed", action='store_true',
                                help="move validated releases into the root scan directory")
    argparser_move.add_argument("--move-fixed-to", help="move validated releases to another folder")

    argparser.add_argument("--move-invalid", help="move releases which fail this validation to a directory")
    argparser.add_argument("--move-invalid-to", help="destination directory for releases which fail validation")

    argparser.add_argument("--move-duplicate-to", help="destination directory for valid releases which already exist")
    argparser.add_argument('--expunge-comments-with-substring', help="remove comments which contain a substring")

    return argparser.parse_args()


def print_list(list_to_print: List[Violation]) -> None:
    for v in list_to_print:
        print(v)
    if list_to_print:
        print()


def list_releases(release_dirs: List[str]) -> None:
    """List releases found in the scan directory"""

    print("Found release directories:")
    num = 0
    for curr in release_dirs:
        print(curr)
        num += 1
    print("Total: {0}".format(num))


def format_violations_str(old_violations: List[Violation], fixed_violations: Optional[List[Violation]] = None) -> str:
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

    # assemble_discs(release_dirs, False)

    for curr_dir in release_dirs:
        audio, non_audio, unreadable = load_directory(curr_dir)
        release = Release(audio, guess_category_from_path(curr_dir), guess_source_from_path(curr_dir))

        codec_short = not args.full_codec_names
        violations = validator.validate(release)
        validate_folder_name(release, violations, os.path.split(curr_dir)[1], False, codec_short)
        add_unreadable_files(violations, unreadable)

        print("{0} violations: {1}".format(format_violations_str(violations), curr_dir))

        if args.show_violations:
            print_list(violations)


def guess_category_from_path(path: str) -> Optional[ReleaseCategory]:
    """Extract a release category from a path. Defaults to Album if none can be inferred"""

    # check if up to 3 parent directories are an exact match of a category
    parent_dirs = path.split(os.path.sep)
    parent_dirs = parent_dirs[-4:-1] if len(parent_dirs) > 3 else parent_dirs
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
        if release_dir.lower().endswith(" {0}".format(category.value.lower())) \
                or " {0} ".format(category.value.lower()) in release_dir.lower():
            return category

    # check if the category is in the middle of the release folder name, surrounded by certain characters
    for category in [x for x in ReleaseCategory if x is not ReleaseCategory.ALBUM]:
        if re.search("(?i)[-_\[{( ]" + category.value + "[-_\]}) $]", release_dir):
            return category

    # default to album
    return ReleaseCategory.ALBUM


def guess_source_from_path(path: str) -> ReleaseSource:
    """Extract a release source from a path. Defaults to CD if none can be inferred"""

    # check if up to 3 parent directories are an exact match of a category
    parent_dirs = path.split(os.path.sep)
    parent_dirs = parent_dirs[-4:-1] if len(parent_dirs) > 3 else parent_dirs
    parent_dirs.reverse()

    for source in ReleaseSource:
        for curr_dir in parent_dirs:
            if curr_dir.lower() == source.value.lower():
                return source

    bracket_pairs = [["[", "]"], ["(", ")"], ["{", "}"]]
    release_dir = str(os.path.split(path)[1]).lower()

    # check if "[Source]" is contained in the release folder name
    for source in [x for x in ReleaseSource if x != ReleaseSource.UNKNOWN]:
        for brackets in bracket_pairs:
            if "{0}{1}{2}".format(brackets[0], source.value.lower(), brackets[1]) in release_dir:
                return source

    # check if the release folder name ends with a space and a source name, without brackets
    for source in [x for x in ReleaseSource if x != ReleaseSource.UNKNOWN]:
        if release_dir.lower().endswith(" {0}".format(source.value.lower())) \
                or " {0} ".format(source.value.lower()) in release_dir.lower():
            return source

    # check if the source is in the middle of the release folder name, surrounded by certain characters
    for source in [x for x in ReleaseSource if x not in [ReleaseSource.CD, ReleaseSource.UNKNOWN]]:
        if re.search("(?i)[-_\[{( ]" + source.value + "[-_\]}) $]", release_dir):
            return source

    return ReleaseSource.CD


def assemble_discs(release_dirs: Iterator[str], move_folders: bool) -> None:
    """
    Directories which contain non-nested discs belonging to the same release are problematic. Solve this by grouping
    disc directories via their lowercase prefix, and move them inside a created release directory
    """

    consolidate = {}

    for curr in release_dirs:
        parent, folder = os.path.split(curr)
        match = re.findall(r'(?i)( )?([(\[{ ])?(disc|disk|cd|part)( ?)(\d{1,2})([)\]}])?', folder)

        if match:
            # skip if the character preceding the disc variant is an alphanumeric character
            if folder.find(match[0][2]) > 0 and folder[folder.find(match[0][2]) - 1].isalnum():
                continue

            container = os.path.join(parent, folder.replace(''.join(match[0]), ""))
            container = re.sub(r' \[[\w]+\]', '', container)

            # create a map[path.lower() -> [path, set[path1, path2...]]
            if container.lower() not in consolidate:
                consolidate[container.lower()] = [container, {folder}]
            else:
                consolidate[container.lower()][1].add(folder)

    # only consolidate releases with more than one disc present
    consolidate = {key: consolidate[key] for key in consolidate if len(consolidate[key][1]) > 1}

    # unpack
    consolidate = {item[0]: item[1] for item in consolidate.values()}

    # in fix mode, create a parent folder and consolidate
    if move_folders:
        for release_path in consolidate:
            # create a container directory
            os.makedirs(release_path, exist_ok=True)

            # move each disc into the container
            for disc in consolidate[release_path]:
                source = os.path.join(os.path.split(release_path)[0], disc)
                os.rename(source, os.path.join(release_path, disc))


def enforce_max_path(path: str) -> None:
    for curr in os.scandir(path):
        curr_full_path = os.path.join(path, curr)
        if len(curr_full_path) > 255:
            if len(os.path.split(curr_full_path)[0]) >= 245:
                raise ValueError("Path is too long: {0}".format(os.path.split(curr_full_path)[0]))
            curr_prefix, curr_ext = os.path.splitext(curr_full_path)
            new_full_path = curr_prefix[:255-len(curr_ext)-2] + ".." + curr_ext
            if not os.path.exists(new_full_path):
                os.rename(curr_full_path, new_full_path)


def fix_releases(validator: ReleaseValidator, release_dirs: Iterator[str], args: argparse.Namespace,
                 dest_folder: str, invalid_folder: str, duplicate_folder: str) -> None:
    """Fix releases found in the scan directory"""

    unique_releases = set()

    for curr_dir in release_dirs:
        if not can_lock_path(curr_dir):
            logging.getLogger(__name__).error("Could not lock directory {0}".format(curr_dir))
            continue

        audio, non_audio, unreadable = load_directory(curr_dir)

        release = Release(audio, guess_category_from_path(curr_dir), guess_source_from_path(curr_dir))

        fixed = validator.fix(release, os.path.split(curr_dir)[1])

        if not args.dry_run:
            for x in fixed.tracks:
                if fixed.tracks[x] != release.tracks[x] or fixed.tracks[x].always_write:
                    cleartag.write_tags(os.path.join(curr_dir, x), fixed.tracks[x])

        # rename files
        rename_files(fixed, curr_dir, args.dry_run)

        new_tracks = OrderedDict()
        for x in fixed.tracks:
            correct_filename = fixed.tracks[x].get_filename(fixed.is_va())
            if correct_filename:
                new_tracks[correct_filename] = fixed.tracks[x]
            else:
                new_tracks[x] = fixed.tracks[x]
        fixed.tracks = new_tracks

        # calculate violations before and after fixing
        codec_short = not args.full_codec_names
        old_violations = validator.validate(release)
        validate_folder_name(release, old_violations, os.path.split(curr_dir)[1], False, args.group_by_category,
                             codec_short)
        add_unreadable_files(old_violations, unreadable)

        violations = validator.validate(fixed)
        validate_folder_name(fixed, violations, os.path.split(curr_dir)[1], True, args.group_by_category, codec_short)
        add_unreadable_files(violations, unreadable)

        if len(violations) == 0:
            moved_dir = move_rename_folder(fixed, unique_releases, curr_dir, dest_folder, duplicate_folder, args)
        else:
            moved_dir = move_invalid_folder(curr_dir, invalid_folder, violations, args.move_invalid)

        enforce_max_path(moved_dir)

        print("{0} violations: {1}".format(format_violations_str(old_violations, violations), moved_dir))

        if args.show_violations:
            if old_violations:
                print("Before")
                print_list(old_violations)

            if violations:
                print("After:")
                print_list(violations)


def move_invalid_folder(curr_dir: str, invalid_folder: str, violations: List[Violation], move_invalid: str) -> str:
    if not invalid_folder:
        return curr_dir

    relocated_dir = curr_dir

    dest = os.path.join(invalid_folder, os.path.split(curr_dir)[1])

    if not os.path.exists(dest) and move_invalid in [x.violation_type.value for x in violations]:
        os.rename(curr_dir, dest)
        relocated_dir = dest

    return relocated_dir


def move_rename_folder(release: Release, unique_releases: Set[Tuple], curr_dir: str, dest_folder: str,
                       duplicate_folder: str, args: argparse.Namespace) -> str:
    """Rename a release folder, and move to a destination folder"""

    # if a dry run,or the folder name cannot be validated, do nothing
    if args.dry_run or not release.can_validate_folder_name():
        return curr_dir

    moved_dir = curr_dir

    # rename the release folder
    codec_short = not args.full_codec_names
    fixed_dir = os.path.join(os.path.split(curr_dir)[0],
                             release.get_folder_name(codec_short=codec_short, group_by_category=args.group_by_category))
    if curr_dir != fixed_dir:
        if not os.path.exists(fixed_dir) or os.path.normcase(curr_dir) == os.path.normcase(fixed_dir):
            while True:
                try:
                    os.rename(curr_dir, fixed_dir)
                    break
                except PermissionError:
                    logging.getLogger(__name__).error("PermissionError: could not rename directory to {0}"
                                                      .format(fixed_dir))
                    time.sleep(1)

            moved_dir = fixed_dir
        else:
            logging.getLogger(__name__).error("Release folder already exists: {0}".format(fixed_dir))

    # move the release folder to a destination
    moved_duplicate = False
    if dest_folder and release.num_violations == 0:
        artist_folder = flatten_artists(release.validate_release_artists()) \
            if args.group_by_artist and not release.is_va() else ""

        category_folder = str(release.category.value) if args.group_by_category else ""
        curr_dest_parent_folder = os.path.join(dest_folder, category_folder, artist_folder)
        curr_dest_folder = os.path.join(curr_dest_parent_folder,
                                        release.get_folder_name(codec_short=codec_short,
                                                                group_by_category=args.group_by_category))

        if os.path.normcase(moved_dir) != os.path.normcase(curr_dest_folder):
            if not os.path.exists(curr_dest_parent_folder):
                os.makedirs(curr_dest_parent_folder, exist_ok=True)
            if not os.path.exists(curr_dest_folder):
                os.rename(moved_dir, curr_dest_folder)
                moved_dir = curr_dest_folder

                # clean up empty directories
                curr_src_parent_folder = os.path.split(fixed_dir)[0]
                while not os.listdir(curr_src_parent_folder):
                    os.rmdir(curr_src_parent_folder)
                    curr_src_parent_folder = os.path.split(curr_src_parent_folder)[0]
            else:
                if duplicate_folder:
                    release_folder_name = release.get_folder_name(codec_short=codec_short,
                                                                  group_by_category=args.group_by_category)
                    moved_dir = move_duplicate(duplicate_folder, moved_dir, release_folder_name)
                    moved_duplicate = True

                else:
                    logging.getLogger(__name__).error("Destination folder already exists: {0}".format(fixed_dir))

    # deduplicate versions of the same release
    unique_release = UniqueRelease(release.validate_release_artists(), release.validate_release_date().split("-")[0],
                                   release.validate_release_title(), release.validate_codec(), release.get_codec_rank(),
                                   moved_dir)

    if duplicate_folder and release.num_violations == 0 and not moved_duplicate:
        if unique_release in unique_releases:
            existing = [x for x in unique_releases if x == unique_release][0]
            if unique_release > existing:
                # move the existing one
                release_folder_name = os.path.split(existing.path)[1]
                moved_dir = move_duplicate(duplicate_folder, existing.path, release_folder_name)
                unique_releases.remove(unique_release)
                unique_releases.add(unique_release)
            else:
                # move the current one
                release_folder_name = release.get_folder_name(codec_short=codec_short,
                                                              group_by_category=args.group_by_category)
                moved_dir = move_duplicate(duplicate_folder, moved_dir, release_folder_name)

        else:
            unique_releases.add(unique_release)

    return moved_dir


def move_duplicate(duplicate_folder: str, source_folder: str, release_folder_name: str) -> str:
    attempt = 0
    while True:
        curr_dest_folder = os.path.join(duplicate_folder, release_folder_name)
        if attempt:
            curr_dest_folder += "_{0}".format(attempt)
        if not os.path.exists(curr_dest_folder):
            os.rename(source_folder, curr_dest_folder)
            return curr_dest_folder
        attempt += 1


def guess_group_by_category(src_folder: str, dest_folder: str) -> bool:
    """Guess if group_by_catetory is desirable"""
    scan_folder = dest_folder if dest_folder else src_folder

    if os.path.split(scan_folder)[1] in {item.value for item in ReleaseCategory}:
        return True

    for curr in os.scandir(scan_folder):
        if curr.name not in {item.value for item in ReleaseCategory}:
            return False

    return True


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

    invalid_folder = None
    if args.move_invalid:
        if args.move_invalid not in [v.value for v in ViolationType]:
            raise ValueError("Invalid violation type '{0}', must be one of {1}"
                             .format(args.move_invalid, ", ".join([v.value for v in ViolationType])))
        if not args.move_invalid_to:
            raise ValueError("--move-invalid must be accompanied by --move-invalid-to")
        invalid_folder = os.path.abspath(args.move_invalid_to)
        if not os.path.isdir(invalid_folder):
            raise ValueError("Destination folder for invalid releases does not exist")

    duplicate_folder = None
    if args.move_duplicate_to:
        duplicate_folder = os.path.abspath(args.move_duplicate_to)
        if not os.path.isdir(duplicate_folder):
            raise ValueError("Invalid duplicates folder: {0}".format(duplicate_folder))

    # guess group_by_category, if it was not set, using the contents of the destination folder
    if not args.group_by_category:
        args.group_by_category = guess_group_by_category(src_folder, dest_folder)

    if args.mode == "releases":
        list_releases(get_release_dirs(src_folder))

    elif args.mode in ["validate", "fix"]:
        lastfm = LastfmCache(lastfmcache_api_url=get_lastfmcache_api_url())
        lastfm.enable_file_cache(86400 * 365 * 5)

        validator = ReleaseValidator(lastfm)

        if args.expunge_comments_with_substring:
            validator.add_forbidden_comment_substring(args.expunge_comments_with_substring)

        if args.mode == "validate":
            validate_releases(validator, get_release_dirs(src_folder), args)

        elif args.mode == "fix":
            assemble_discs(get_release_dirs(src_folder), True)
            fix_releases(validator, get_release_dirs(src_folder), args, dest_folder, invalid_folder, duplicate_folder)

def get_root_dir() -> str:
    """get the root directory of the script"""
    if getattr(sys, 'frozen', False):
        return sys._MEIPASS

    return os.path.dirname(os.path.abspath(__file__))


def get_lastfmcache_api_url() -> str:
    root_dir = get_root_dir()
    ini_filename = "config.ini"

    if not os.path.isfile(os.path.join(root_dir, ini_filename)):
        shutil.copy(os.path.join(root_dir, "ini_template"), os.path.join(root_dir, ini_filename))

    config = configparser.ConfigParser()
    config.read(os.path.join(root_dir, ini_filename))

    if 'lastfmcache' not in config:
        raise ValueError("Invalid {0} config file".format(ini_filename))
    if not config['lastfmcache'].get('api_url'):
        logging.getLogger(__name__).error("lastfmcache API URL missing from {0}".format(ini_filename))
        exit(1)

    return config['lastfmcache']['api_url']


def load_config():
    root_dir = get_root_dir()
    ini_filename = "config.ini"

    if not os.path.isfile(os.path.join(root_dir, ini_filename)):
        shutil.copy(os.path.join(root_dir, "ini_template"), os.path.join(root_dir, ini_filename))

    config = configparser.ConfigParser()
    config.read(os.path.join(root_dir, ini_filename))

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
