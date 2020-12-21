# centrifuge

Standardize and validate music file names, directory names, directory hierarchies and metadata

 Centrifuge scans an input directory structure and reorganizes a music library into a standardized file/directory 
 structure. 
 Releases are deduplicated, and metadata is validated using last.fm. 
 
 Validated releases can be moved into a destination directory, making it easy to identify problematic data for manual 
 replacement or deletion. Folders which contain incomplete releases, invalid/incomplete metadata, or were encoded with 
 inconsistent settings  are considered invalid. Where possible, automated fixes can be applied to the metadata and 
 file/directory names.
 
 Releases can be grouped in subdirectory by category (e.g. album, single, EP, compilation) and/or by artist. It is 
 highly recommended to group by release category.
 
 A validated directory structure looks like the following, at the top level:
 ```
Music
|- Album
|- Anthology
|- Bootleg
|- CDM
|- Compilation
|- Concert Recording
|- Demo
|- EP
|- Interview
|- Live Album
|- Mix
|- Mixtape
|- Remix
|- Single
|- Soundtrack
\- Video Game Music
```

Release directory names are typically in the form `Artist - Year - Title [encoder setting]`. Release directories with a
category other than Album also contain the category in square brackets, in the form 
`Artist - Year - Title [Category] [encoder setting]`.  


The validation process involves querying last.fm for each artist and release. This is a time consuming process when a
large collection is scanned for the first time. Results are cached, and subsequent scans are significantly faster.

### Getting started

Centrifuge has three modes - `validate`, `fix`, and `releases`. `fix` is the most useful mode.

It can be useful to move validated releases to a different directory on the initial scan of your collection. The 
following example scans `C:\Unsorted music` and moves validated releases into `C:\Music`, grouping releases by category
similar to the 

`centrifuge fix "C:\Unsorted music" --move-fixed-to "C:\Music" --group-by-category`

After the first scan completes, you may have some releases in the wrong category subdirectory. Live albums, mixes, 
sound tracks, compilations and other release categories can be manually moved into a correct directory. The scanner can
be rerun, in-place, and will correct the titles of the moved release directories:

`centrifuge fix "C:\Unsorted music" --move-fixed-to "C:\Music" --group-by-category`

### Advanced usage

Print out a list of releases in a directory structure: `centrifuge releases C:\Music`

Validate only: `centrifuge validate`

Group by release category and by artist: `centrifuge fix "C:\Music" --group-by-artist --group-by-category`

Move duplicates to a separate directory: 
`centrifuge fix "C:\Unsorted music" --group-by-category --move-duplicate-to "C:\duplicate music"`

Move releases which fail a specific validation to a separate directory. This mode is useful when applying specific 
external fixes to a large set of invalid releases: `centrifuge fix "C:\Unsorted music"  --group-by-category --move-invalid codecs-inconsistent --move-invalid-to C:\broken`

The full set of `--move-invalid parameters`:

    artist-whitespace, release-artist-whitespace, date-whitespace, release-title-whitespace, track-title-whitespace, 
    genre-whitespace, date-inconsistent, artist-blank, track-title-blank, release-artist-inconsistent, 
    release-artist-spelling, release-artist-not-found, release-title-inconsistent, release-title-category, 
    release-title-source, release-title-spelling, date-incorrect, bad-genres, incorrect-track-title, 
    track-artist-spelling, missing-tracks, total-tracks, missing-discs, total-discs, tag-types, codecs-inconsistent, 
    cbr-inconsistent, filename, folder-name, artist-lookup, unreadable, comment-substring

### Other options

`--show-violations`: print validation failures.

`---move-fixed` is an alternative to `--move-fixed-to`. Fixed/validated releases are moved into the correct directory
inside the source directory structure, based on the root.

`--expunge-comments-with-substring` searches for 'comment' tags which contain a given substring, and erases the entire 
comment if there is a match. 

`--full-codec-names` adds full codec names to release directory titles (for example, `[MP3 CBR320]` instead of 
`[CBR320]`).