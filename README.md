# Desk

Desk is a local research workbench for projects, tasks, meetings, journals and reading notes. It stores records as Markdown with YAML frontmatter so you can also work on them in a text editor or Obsidian.

## Install on macOS

Download the DMG from [GitHub Releases](https://github.com/masite123/Desk/releases), open it, and drag **Desk** into **Applications**. Open Desk from Applications. It starts a local server and opens your default browser. Quit Desk from its menu to stop the server.

The installer includes Python and supports Apple Silicon Macs running macOS 15 or later. It uses ad hoc signing and has no Apple notarization. macOS may block the first launch. If you trust the download and have verified the published SHA-256, see [Apple’s instructions for approving an app](https://support.apple.com/en-us/102445).

The installed app stores records under `~/Library/Application Support/Desk`. Your records stay in that folder when you replace the app.

## Run from source

Use Python 3.11 or later on macOS or a compatible Unix-like system. This source package was tested on macOS. Desk uses Unix file locks, so native Windows support would require a port.

Download and extract the source archive, or clone the repository.

```sh
git clone https://github.com/masite123/Desk.git
cd Desk
```

From the Desk folder, run the workspace check and start the app.

```sh
python3 .system/app/phd.py check
python3 .system/app/phd.py launch
```

Open [Desk in your browser](http://127.0.0.1:8766/) if it does not open automatically. Keep the terminal running and press Ctrl+C to stop the server you started. If your existing Desk uses port 8766, pass `--port 8767` and open [port 8767](http://127.0.0.1:8767/).

Use **Projects → Project** to start a project, or **Tasks → Add task** to create a standalone task. Desk starts with an empty workspace. It creates record folders as you add records.

## Dependencies and build

The backend uses Python's standard HTTP server, SQLite for the literature queue and `fcntl` for local locks. The frontend is plain HTML, CSS and JavaScript. PyYAML 6.0.3 and pypdf 6.18.0 ship with the source, including their license notices, so the core app requires no package installation. See [vendored dependencies](.system/app/vendor/README.md).

```sh
python3 .system/app/phd.py build
python3 .system/app/phd.py serve
```

The build generates `Home.md`, `.system/index/dashboard.html` and `.system/index/records.json`. The dashboard uses the running server for editing and file access. Run `serve` by itself to build and start without opening a browser.

| Optional feature | Requirement |
| --- | --- |
| Edit records in Obsidian | Open the Desk folder as a vault |
| Refresh Zotero metadata | Run Zotero with its local API enabled. Desk reads Zotero and saves a local copy of metadata |
| Generate PDF covers | Put Poppler's `pdftoppm` on your PATH and run `python3 .system/app/refresh_covers.py` |
| Citation enrichment | Network access to metadata providers such as Crossref and OpenAlex |
| Agent-assisted PDF intake, reading and comparison | A working, authenticated Codex CLI. These actions can send extracted document text to the model service. Use documents you are authorized to share |

## Workspace data

Desk is intended for one trusted user on localhost. Use trusted workspace files and keep the server on loopback. It has no account system for network use. Calendar records are local.

- `Records/` and registered paper folders under `Materials/` contain the canonical records and attachments.
- `.system/config/registry.example.json` is the shipped default. Copy it to `.system/config/registry.json` to customize record roots or linked material paths. Zotero refresh can also write the local registry.
- `.system/context/current.md` is an optional local handoff included in the generated index.
- Local records, attachments, generated views, job data and local configuration are ignored by Git. Back them up separately from this source repository.

## Development and source release

```sh
python3 -m unittest discover -s .system/tests
for test in .system/tests/*.cjs; do node "$test" || exit 1; done
```

Node.js is used only for JavaScript tests. From a committed checkout, create a source ZIP containing tracked files:

```sh
git archive --format=zip --prefix=desk/ --output=../desk-source.zip HEAD
```

To build the Apple Silicon DMG, install the Xcode Command Line Tools and download the [pinned Python runtime](packaging/macos/Runtime.md). From a clean, committed checkout, run:

```sh
packaging/macos/build.sh /path/to/cpython-3.13.18+20261026-aarch64-apple-darwin-install_only_stripped.tar.gz
```

The DMG and its SHA-256 file are written to `dist/`. The macOS installer includes the browser launcher. Calendar records are local and the installer does not set up notification reminders.

## Licensing

Desk is distributed under the [MIT License](LICENSE). Third-party dependencies retain their own license notices under `.system/app/vendor/`.
