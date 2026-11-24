# GitHub Accesible

[Versión en español](README.md)

A Windows desktop application for working with **all of GitHub and local git from the keyboard and with a screen reader** (NVDA, JAWS or Narrator). It is available in Spanish and English (it picks the Windows language automatically, and you can change it in Preferences), every screen is designed to sound right, and nothing requires the mouse or the website.

- Author: Héctor J. Benítez Corredera.
- License: GPL version 3 (see [LICENSE](LICENSE)).
- Downloads: [GitHub releases](https://github.com/hxebolax/GithubAccesible/releases) and [the author's server](https://xebolax.synology.me/GithubAccesible/).

## For users

### What it is and why it exists

The GitHub website is usable with a screen reader, but some everyday tasks are very tedious: reading the diff of a pull request, commenting on a specific line, following the log of an Actions run, resolving merge conflicts or moving cards in a project. GitHub Accesible turns all of that into native Windows lists, with columns you can read one at a time, sounds that tell you what is happening and keys that jump straight to what matters.

### What it can do

#### Accounts and sign-in

- Sign in **with the browser and a code** (the most secure option: your password, two-factor authentication or passkey are used on the website, never in the application).
- Sign in with a **personal access token**, classic or fine-grained, with buttons that open GitHub with the permissions already selected.
- **Import the GitHub CLI session** (`gh`) or your **Git credentials** if you already have them on your computer.
- **Multiple accounts** at once and **GitHub Enterprise Server**. Tokens are stored encrypted with your Windows user account.

#### Main window

A list of sections on the left and its content on the right:

- **Home**: activity from the people and repositories you follow.
- **Notifications**: open, mark as read or done, mute conversations. They are checked automatically in the background and announced with speech and sound (a different one if you are mentioned or asked for a review).
- **My repositories**, **Starred repositories** and **Watched repositories**: open, clone, star, fork, create and delete.
- **My issues** and **My pull requests**: assigned, created, mentions, review requests.
- **Gists**, **Organizations**, **Projects**, **Codespaces**, **Followers** and **Following**.
- **Local repositories**: the git folders on this computer.
- **Search** on GitHub: repositories, code, issues, users, commits and topics, with the full qualifier syntax.

#### Repository window

Overview and formatted README, code browser, issues, pull requests, discussions, GitHub Actions, releases, branches, tags, commits, projects, milestones, issue labels, collaborators, forks, watchers, security (Dependabot, code scanning and secret scanning), environments, Actions secrets and variables, webhooks, deploy keys, rules and branch protection, statistics and traffic, deployments, GitHub Pages and full repository settings.

#### Issues and pull requests

- The full conversation in a list (description, comments and events), with the complete text of the focused item.
- Comment, quote reply, edit, react, close, reopen, labels, assignees, milestones, lock and transfer.
- **Attach text files** (`.log` files, for example) to issues, pull requests, discussions and comments: collapsed inside the text or uploaded to a secret gist with its link.
- Pull requests with tabs for conversation, commits, files changed, checks and review threads.
- **Line-by-line review**: Enter on a diff line comments on it; commented lines are marked and announced; you can approve, request changes, resolve threads and merge (merge, squash or rebase).

#### Diff viewer

Each line is a row with its type (“Added”, “Removed”, “Unchanged”), its number and its text, with a different sound for each type. F8 jumps to the next group of changes, Control+F8 to the next hunk and F7 to the next file.

#### GitHub Actions

Runs, jobs and steps in lists; a clean log (without color codes or timestamps) with F8 to jump to the next error; annotations; re-run, cancel, approve deployments, download artifacts and trigger workflows with their inputs. It follows a run live and notifies you when it finishes.

#### More of GitHub

Releases (create them with automatic notes, upload and download assets), a **download manager** (several at a time, they continue even if you close the window, with pause, resume and errors explained), gists, discussions, projects (with “Move to…” instead of dragging), profiles, organizations and teams, SSH and GPG keys (including generating a new SSH key), GitHub status and API rate limit.

#### Local git

Changes with stage and unstage, commit (including amend and sign), history with diffs, branches, tags, stash, remotes, fetch, pull and push with spoken progress, cherry-pick, revert, reset, reflog, submodules, worktrees, guided bisect and **hunk-by-hunk conflict resolution** (“your version” or “the other one”, also during rebases). Clone with progress and cancellation.

### Accessibility

- Native Windows controls: the screen reader announces name, type and state without tricks.
- **Lists read by columns**: Left Arrow and Right Arrow move through the columns; Control plus a number reads a column directly. In Preferences you choose whether the row number, the column name and the content are read.
- **Configurable columns for each list**: which ones are shown and in what order (and therefore what the screen reader reads, and in what order).
- **Checkbox lists** that announce their state; you can choose to hear the state before or after the text, and the position.
- **You move the focus**: moving through the sections or choosing in a combo box changes what is shown, but the focus does not jump anywhere until you ask for it (Tab, Enter or F6).
- Help for any control with Control+H and the full user guide with F1. In Preferences you choose whether the screen reader also reads that help when you reach buttons and checkboxes, and on each row of checkbox lists.
- Sounds for each event, with volume, sound packs and events that can be turned off one by one.
- A history of spoken announcements so you can hear again what was said.
- README, user guide and long texts in HTML that you can navigate by headings (or in plain text if you prefer).
- The interface never freezes: everything that takes time runs in the background.

### Installation

1. Download the latest `GithubAccesible_vX.Y.Z.zip` from the releases or from the author's server.
2. Extract it wherever you like (for example, in `Documents` or on a USB drive).
3. Run `GithubAccesible.exe`.

It is **portable**: nothing is installed on the system, and everything the application saves (settings, logs, custom sounds) stays in its `data` folder. To uninstall it, just delete the folder. To use local git you need [Git for Windows](https://git-scm.com) installed.

### Updates

The application checks for new versions at startup and once a day (this can be turned off). In **Preferences, Updates** you choose the source:

- The author's server and, if it does not respond, GitHub (default).
- Only the author's server.
- Only GitHub releases.
- A custom address.

Every version is **digitally signed**: the application rejects any package that does not carry the author's signature. A backup is made before anything is replaced, your data in `data` is never touched and, if the new version does not start correctly, it automatically rolls back to the previous one.

### Main keys

- F6: switch between the section list and its content.
- Alt+1 to Alt+9 and Alt+0: go to each section.
- Enter: open the item. Applications key or Shift+F10: its actions.
- F5: refresh. Control+F: filter the list. Control+B: open in the browser. Control+I: full details.
- Control+O: open a repository by name or link. Control+E: search GitHub.
- Control+P: Preferences. F1: user guide. Shift+F1: full list of keyboard shortcuts.

The full list is in [docs/en/teclas.md](docs/en/teclas.md) and the user guide in [docs/en/manual.md](docs/en/manual.md).

### Support the project

If you find the application useful, you can buy the author a coffee from the Help menu, “Buy me a coffee if you like my work”.

## For developers and contributors

### Requirements

- Windows 10 or 11, 64-bit.
- [Python 3.15](https://www.python.org) (the project uses `py -3.15`).
- Git for Windows (for the local git tests).

Main dependencies: wxPython 4.3.2, requests, Markdown, cryptography and accessible_output2. Development: cx_Freeze 8.7, pytest, ruff, comtypes and PyNaCl.

### Environment and common tasks

Everything is done with `entorno.bat`, which has an accessible menu and also accepts direct commands:

```
entorno.bat crear
entorno.bat ejecutar
entorno.bat pruebas
entorno.bat compilar
```

- `crear`: creates `.venv` with Python 3.15 and installs `requirements.txt` and `requirements-dev.txt`.
- `ejecutar`: runs the application from source.
- `pruebas`: runs the pytest suite.
- `compilar`: builds with cx_Freeze (with the Visual C++ runtimes and `WebView2Loader.dll`), checks that the build is complete and clean, and generates the ZIP and `version.json`.

Without the menu: `.venv\Scripts\python.exe -m pytest` and `.venv\Scripts\python.exe main.py --comprobar-arranque`.

### Publishing a version

1. Change `APP_VERSION` in `app/core/version.py` (the single source of the version) and `version` in `pyproject.toml`.
2. Add the release notes to `docs/changelog.md` and, translated, to `docs/en/changelog.md` (the same version in both).
3. Run `.venv\Scripts\python.exe tools\publicar.py`. It builds, packages, signs `version.json` with the private key in `tools/claves/` (which is never pushed to the repository), copies the ZIP and the manifest to the folder synchronized with the server, and creates the GitHub release with `gh`.

The private signing key is essential to publish versions that existing installations will accept: keep a copy off the computer.

### Sign-in with the browser (OAuth app)

Signing in “with the browser and a code” needs the Client ID of an OAuth app with “Enable Device Flow” checked. It is public information (no client secret is used). How to register it, test it from Preferences and set it permanently in `ID_CLIENTE_OAUTH` is explained in [docs/en/oauth.md](docs/en/oauth.md).

### Structure

- `main.py`: startup in the right order, with a safety net.
- `app/core`: portable paths, version, configuration, encrypted secrets (DPAPI), logging, background tasks, translation, shared context.
- `app/services`: logic without an interface. `github/` (REST and GraphQL client, authentication, the whole API by area), `git_local.py`, `diferencias.py`, `conflictos.py`, `sonidos.py`, `formato.py`, `actualizador.py`.
- `app/ui`: interface. `accesibilidad/` (lists, checkboxes, dialogs, speech, keyboard), `vistas/` (list and section framework), `repositorio/`, `detalle/` (issues, pull requests, diffs, Actions, releases...), `git/`, `herramientas/`, preferences, sign-in.
- `tests`: pytest tests, without network access and without touching the real `data`.
- `tools`: build, packaging, signing, publishing, translations and shortcut checks.
- `docs`: user guide, keyboard shortcuts and changelog in Spanish; `docs/en`, the same in English.
- `data/locales`: translation template (`.pot`) and English catalog (`en/LC_MESSAGES/githubaccesible.po` and `.mo`).
- `adjuntos`: research and reference repositories used during development (not distributed).

### Conventions

- Code indented with tabs and checked with `ruff` (`.venv\Scripts\ruff.exe check .`).
- Spanish is the main language and English the secondary one. Code, comments and logs are in Spanish; every text the user sees or hears is marked with `_()` (or `N_()` in tables) and translated in the English catalog, and every document in `docs/` has its version in `docs/en/`.
- To translate: `tools\extraer_cadenas.py`, `tools\actualizar_po.py`, translate the new strings in `data/locales/en/LC_MESSAGES/githubaccesible.po` and `tools\compilar_traducciones.py`.
- Accessibility is mandatory: a label created before each control, access keys not repeated on any screen and in both languages (there are tests that check this), buttons in the interface language, nothing that blocks the interface.
- No error is lost: everything is recorded in `data/logs` with file, line and traceback, and tokens are masked in the logs.

### License

GPL version 3. Copyright (C) 2026 Héctor J. Benítez Corredera.
