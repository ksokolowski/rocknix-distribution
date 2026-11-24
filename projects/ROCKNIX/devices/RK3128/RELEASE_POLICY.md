# Public release policy (Powkiddy A12 / A13)

A public release (a GitHub pre-release of the fork and its `a12/port`
export) is published only when all of the following hold.
`tools/a12-release-audit` checks every rule it can; a finding stops the
release, it is not a warning.

## Content

- No commercial game data: no ROMs, disc images, BIOS or firmware dumps
  (console BIOS, Amiga Kickstarts, Roland MT-32 ROMs and the like) and no
  game files of any kind, in the image or in the source export.
- Every game, ROM-type, BIOS-like or large data file in the image is listed
  in [`release-content.tsv`](release-content.tsv) with its licence and
  source. A new bundled file needs a new line there, reviewed with the
  change that adds it.
- The audit compares file checksums with known BIOS images and with the
  files of the owner's own BIOS folder, wherever such a file sits.

## Credentials and private data

- The only credential in an image is the ScreenScraper developer login that
  ScreenScraper publishes for JELOS-based builds, compiled into
  EmulationStation with the software name `ROCKNIXA12`. It is supplied at
  build time and never committed.
- No personal accounts, passwords, keys or tokens.
- No private identifiers (home network addresses, host names, MAC
  addresses, home paths, personal accounts) in the image, the export or the
  release notes. The audit reads them from a local pattern file that is not
  part of the repository.

## Source export

- `a12/port` is one squashed export of the code the release was built
  from. It matches that revision apart from the owner's private documents
  (test log, bring-up notes, backlog, plans, upstream tracker, agent
  instructions), which are never exported.

## Testing

- The published update tar is the one a hardware test installed: its
  checksum is named in the owner's test log, and the card image carries the
  same system image as that tar.
- Known issues in the release notes cover what was not rechecked.

## Release notes

- Written in the owner's voice, describing user-visible changes, install
  and update steps, known issues and the source.
- No notes about AI assistance.

## Procedure

1. Build the image from the release revision with the build environment
   that supplies the ScreenScraper login.
2. Install the update tar on an A12 or A13 and run the hardware pass; record
   it in the test log with the tar's checksum.
3. Export the code to `a12/port` in the public worktree.
4. Run the audit:

   ```sh
   projects/ROCKNIX/devices/RK3128/tools/a12-release-audit \
     --tar target/ROCKNIX-RK3128.arm-<version>.tar \
     --img target/ROCKNIX-RK3128.arm-<version>-Powkiddy_A12.img.gz \
     --notes <release notes> --testlog projects/ROCKNIX/devices/RK3128/TEST_LOG.md \
     --private <local pattern file> --bios-dir <owner's BIOS folder> \
     --export-repo <public worktree> --export-ref a12/port --source-rev <release revision>
   ```

5. The owner reads the notes and gives the go.
6. Push `a12/port`, tag the export commit, publish the pre-release with the
   notes, the image, the update tar and both `.sha256` files.
