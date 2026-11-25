# What's new in GitHub Accesible

Each version has its own section, from the newest to the oldest. Within each version, changes are grouped into New, Improvements and Fixes, described from the point of view of the person using the application.

## Version 1.0.15 - 2026-11-25

### New

- **Sections refresh automatically** (issue #14). Home, Starred repositories and Watched repositories are refreshed every 5 minutes while they are in view, and when you go back to them. The list changes without moving the focus or losing the item you are on, and you are told how many new items have arrived.
  - Only the section in view and while the window is visible: hidden in the system tray, it uses no requests. If nothing has changed, GitHub does not count it against the limit.
  - Preferences, Lists: turn it on or off, how many minutes between refreshes, when going back to a section, announcing new items, and a checkbox list with the sections that refresh (My repositories, My issues, Gists… too). The explanation of each option says how much API it uses.

### Fixes

- In English, two options in Preferences, Translation and Translation keys, had the same access key as the OK button.

## Version 1.0.14 - 2026-11-24

### New

- **Translator** (issue #13), to read what is written in other languages and to write in yours and send in another:
  - In the conversation of an issue, pull request or discussion, **Ctrl+T** translates the selected item and **Ctrl+Shift+T** the whole conversation, each part with its author.
  - **“Translator”** window (Tools, Ctrl+Shift+Y): more than a hundred source and target languages, language detection, swapping languages, copying and viewing the translation formatted.
  - **“Translate when sending into”** in the editor and in “New issue”: write in Spanish, choose English, for example, and when you send, review and correct the translated title and text before it is sent. You can add the original, collapsed, at the end.
  - Engines to choose from: Google Translate (the default, free and without a key), MyMemory (free) and LibreTranslate; and, with your own key, official Google Translate (Cloud Translation), Microsoft Translator, DeepL and the AI models Gemini, ChatGPT, DeepSeek and Claude, using the cheapest model of each. If the chosen one fails, the free ones are used.
  - Preferences, “Translation” and “Translation keys” (encrypted), with a button to test the engine. Code blocks, links, @mentions and #references are not translated.

## Version 1.0.13 - 2026-11-24

### New

- **Download manager** (Ctrl+Shift+D, Tools, “Downloads”, or the system tray menu). All downloads (release assets, Actions artifacts and logs, code as zip) belong to the application: they continue even if you close the window that started them, and several can download at the same time while you keep working.
  - A list with the status, progress, amount downloaded, speed, time left, source, folder and, if it fails, the error explained.
  - Pause and resume where it left off (Space), retry failed ones, cancel (Delete), open the file (Enter) or its folder (Ctrl+O), remove completed ones, and pause or resume all.
  - A message and a sound when each one finishes or fails, even with the window closed. The SHA-256 checksum of release assets is checked automatically.
  - If you exit with downloads in progress, they are paused and continue on their own when you open the application again.
  - Preferences, Downloads: how many at a time, continue when opening, and open the window when one starts. Plus an optional global hotkey to open it from any program.

## Version 1.0.12 - 2026-11-24

### New

- **A profile's activity no longer stops at the last month.** GitHub only provides the events from the last 30 days; when you reach the end of the list, the application keeps loading the person's earlier contributions year by year, back to when they joined GitHub: commits, opened issues and pull requests, reviews and created repositories. Each year uses 1 point of the 5,000 per hour that GitHub allows; this can be turned off in Preferences, Lists.

## Version 1.0.11 - 2026-11-24

### New

- **Followers** and **Following** show public repositories, followers, how long each person has been on GitHub, their contributions in the last year and the link to their profile.
- **More columns in repository lists** (Preferences, “List columns”): creation date, size, license, topics, website, link, clone with HTTPS and with SSH, watchers, latest release and your permission. “My repositories” shows the creation date by default. Ctrl+I also gives your permission and the latest release.

### Fixes

- **“My issues” was empty** for people who open issues in other people's repositories. Issues are now searched across all of GitHub and the list shows the ones you created by default; F4 switches to assigned, mentions, commented, all you are involved in or the ones in your repositories.
- Ctrl+I on a repository gave the number of stars as the number of watchers.

## Version 1.0.10 - 2026-11-23

### New

- **General settings for the message when an Actions run finishes** (Preferences, Actions), which apply to everything that is watched at once: “Notify me when it finishes”, each repository's “Notify when each Actions run finishes” and the runs triggered by a push.
  - Sound when it finishes, on or off.
  - Result by voice, on or off (by the screen reader or the SAPI 5 voice).
  - Which runs to report: all of them, only the ones that fail or only the ones that succeed.

## Version 1.0.9 - 2026-11-23

### New

- **Messages with a separate SAPI 5 voice** (Preferences, Notifications, “Read background messages with”). New notifications and the end of watched Actions runs can be read by a separate Windows voice, which is not cut off when you press keys the way the screen reader is. You choose the voice, rate and volume, and you can test them before clicking OK. By default the screen reader still reads them.
- **Each section's keys also work from the section list**, in the main window and in a repository window: for example, Ctrl+Shift+A marks all notifications as read and Ctrl+N creates a new issue without going into the list first. Keys that act on an item (Delete, F2…) still work only inside the list, so nothing is changed blindly.

### Improvements

- In the Markdown text of issues, pull requests and comments, **Tab and Shift+Tab move between controls**, as everywhere else in Windows. If you prefer Tab to type a tab character, turn it on in Preferences, Editor.

## Version 1.0.8 - 2026-11-23

### New

- **Sort lists by column**, in every list in the application. Ctrl+J sorts by the column being read: ascending, then descending, then back to the original order. Ctrl+Shift+J (or Actions, “Sort the list”) chooses the column and the direction; with the mouse, click the column header. Dates, numbers and sizes are sorted by their real value, numbers inside text too (“issue 2” before “issue 10”), and items without a value go to the end. Each list remembers its sort order.
- **Mark all notifications as read with Ctrl+Shift+A** in the Notifications section.

## Version 1.0.7 - 2026-11-22

### New

- **The application in English**. Spanish is still the main language and English is the second one: the whole interface, messages, spoken announcements, the user guide, the keyboard shortcuts and what's new are available in both languages.
- **Automatic language**: when it starts, the application uses Spanish if Windows is set to any variant of Spanish (es-ES, es-MX, es-US…) and English for any other language. Existing installations also switch to the Windows language.
- **Choose the language** in Preferences, General, “Interface language”: automatic, Spanish or English. When you change it, the application offers to restart to apply it.
- **Documentation in your language**: F1 (user guide), the keyboard shortcuts and Help, “What's new in this version” open in the interface language. So does what's new after an update and in the “Update available” window; the GitHub page for each version includes it in both languages.

### Improvements

- Dates, numbers and sizes use the format of each language (in English, “Nov 22, 2026” and “1,234”).
- Global hotkeys and menu shortcuts are spoken with the key names of the chosen language (“Shift”, “Del” or “Enter” in English).
- Some messages that used to be assembled from fragments are now spoken as complete sentences, such as “ana pushed 1 commit” (previously “1 commits”) and “created branch dev” (previously a mix of Spanish and English).

## Version 1.0.6 - 2026-11-22

### Improvements

- The “Update available” window now shows what's new: the changes in every version after the installed one, in case you skipped any. Previously it always said that the server had not published any release notes. If there are none, you no longer get an empty box: it says that you will see them when the new version opens.
- What's new, which opens by itself after an update, now always includes the three previous versions as well as the new one: with this version, from 1.0.3 onwards. The GitHub page for the version includes them too.

## Version 1.0.5 - 2026-11-22

### New

- **Configurable system tray** (Preferences, General): besides minimizing and starting in the tray, you can now make closing the window leave it in the tray instead of exiting, and keep the icon always visible. The icon tells you how many unread notifications there are, and its menu lets you go to them, hear them, check for new ones, search and open Preferences. The File menu has “Hide to system tray”.
- **Configurable global hotkeys** that work from any program: Control+Alt+Shift+G shows or hides the application and Control+Alt+Shift+N reads the unread notifications. In Preferences, Global hotkeys, you change them by pressing the combination you want, and you can enable three more (open Notifications, search and check now). If another program already uses one, you are warned.
- **Sections your way** (Preferences, Sections): hide the ones you don't use and put them in the order you prefer, in the main window and in the repository window. Alt plus a number follows the chosen order.
- **Command palette** (Control+Shift+O in any window): type part of the name of what you want to do and run it with Enter; it tells you the shortcut and the menu of each command.
- **Watch Actions runs in the background**: “Notify me when it finishes” on runs in progress (Control+Shift+W), watch all the runs of a repository from its menu, and automatic notification of the result of the runs triggered by a push made from the application. You are notified with speech, a sound and, if you want, a Windows notification. Tools, “Watched Actions runs”, shows what is being watched.
- **Narrated diffs** in the diff viewer: Control+D tells you what changes within a line (“Changes ‘30’ to ‘60’”), Control+Shift+D gives the summary, Control+Shift+T shows the narrated differences as text and F8 says “Change n of m”. Invisible characters and characters that change the direction of the text are shown by name and announced.
- **Issue forms**: the repository's forms are filled in an accessible dialog, with one field per item and the required ones marked, and the issue looks the same as on the web. Text templates keep their title, labels, assignees and type; “Blank issue” and contact links are respected. Pull requests start with the repository's template.

### Fixes

- Control+U (view a profile) failed with a section open in the main window since version 1.0.4.
- The Actions run window and the update dialog no longer give focus to controls of a hidden window.

## Version 1.0.4 - 2026-11-22

### New

- New **Wiki** section in the repository window. It lists the pages (the home page first), opens them formatted in the viewer (links to other wiki pages also open there) and lets you edit them with F2, create pages with Control+N, rename them, delete them, view the history of each one with its old versions and diffs, and search for text in all of them with Control+P. If the wiki is disabled or empty, you are told so and offered to enable it or create the first page in the browser. GitHub does not provide wikis through its API: Git for Windows is required.
- In search results, the actions (Applications key) let you **view the owner** of each result (Control+Shift+P) to open their profile, view their repositories or follow them; view the author of an issue, pull request, discussion or commit; go to its repository (Control+Shift+R); and, for repositories, clone, star, watch and fork. For people found in a search, you can follow or unfollow them without opening their profile.
- In the repository window, the Repository menu has “View owner” (Control+Shift+P).
- “Download the code as zip” is now also in the Repository menu, in the repository lists (mine, starred, watched and those of a profile) and in search results, and it tells you how much has been downloaded.
- In a fork, the Repository menu lets you open the original repository and sync a branch with it, like the “Sync fork” button on the web.
- Control+U (view a profile) suggests the person in the selected row: who did the activity, the author of the issue or commit, or the owner of the repository.
- A person's profile has two new tabs, Starred and Activity, and the “Read profile README” button (Alt+M) with the introduction shown on the web.
- When you download a release asset, the SHA-256 checksum published by GitHub is verified and you are told whether it is correct; you can also copy it.
- In the repository lists, “View wiki” opens that section directly.

### Fixes

- “Download repository as ZIP” gave GitHub error 415 (“Unsupported 'Accept' header”). It now downloads correctly, as do the zip of a tag and the code downloaded when cloning without git.
- In the action menus of the main window (repositories, issues, pull requests, gists, organizations, projects, local repositories, codespaces and search results) there are no longer two commands with the same access key. “Delete repository” deliberately has no access key, so that it cannot be deleted by accident.

## Version 1.0.3 - 2026-11-22

### New

- When you write an issue, a pull request, a discussion or a comment, you can attach text files, such as a `.log` file, with the “Attach file” button (Alt+F). The content goes inside the text, in a collapsed block with the file name, or, if it is very long, it is uploaded to a secret gist and the text includes its link. Slann Tonić asked for it in the project's first issue. GitHub does not allow applications to upload images or other binary files; for those you still need the website.

## Version 1.0.2 - 2026-11-21

### Improvements

- New options in Preferences, Accessibility, to choose whether the screen reader reads the help for each control when you reach it: one for buttons and checkboxes, and another for each row of checkbox lists. The one for rows is off by default: when you move through a checkbox list you only hear each row and its state. Control+H still always reads the help.
- In the window of a local repository, Enter in the section list moves into the content, as in the main window.

### Fixes

- In the search, changing what you search for (repositories, issues, code…) or loading a search from the history or from the saved searches no longer moves the focus to the “Search text in” list: it stays on the combo box.
- In the window of a local repository, moving through the sections no longer puts the focus in the section's list.
- In Preferences, “List columns”, Move up and Move down no longer move the focus to the list: it stays on the button so you can keep moving.

## Version 1.0.1 - 2026-11-21

### New

- You can now sign in with the browser and a code without configuring anything: the application comes with its own GitHub identifier.
- If GitHub issues a token that expires, the application renews it by itself before it expires or when GitHub rejects it, without asking you to sign in again.

### Fixes

- The number of notifications in the section list (“Notifications (2)”) now changes as soon as they are marked as read or done, or the list is refreshed; previously it kept the old number.
- After changing something on GitHub (marking as read, starring, closing…), the lists no longer show old cached data.
- If the OAuth application identifier is wrong, you are told so clearly instead of getting a generic error.

## Version 1.0.0 - 2026-11-21

### New

- First published version.
- Sign in with the browser and a code, with a personal access token, by importing the GitHub CLI session or with the Git credentials. Multiple accounts and GitHub Enterprise Server.
- Main window with Home, Notifications, My repositories, Starred repositories, My issues, My pull requests, Gists, Organizations, Projects, Local repositories, Watched repositories, Followers, Following, Codespaces and Search.
- A window for each repository with everything: code, issues, pull requests, discussions, Actions, releases, branches, tags, commits, projects, milestones, collaborators, security, secrets and variables, webhooks, rules, statistics, Pages and settings.
- Issues and pull requests with the full conversation, line-by-line review, threads, checks and merging.
- Accessible diff viewer: line type, number, sounds and jumps by change, hunk and file.
- GitHub Actions: runs, jobs, steps, clean logs with jumps to errors, artifacts and triggering workflows.
- Full local git: changes, commits, history, branches, stash, tags, remotes, conflicts hunk by hunk and cloning with spoken progress.
- Background notifications with speech, sound and optional Windows notification.
- Accessibility preferences: reading by columns, visible columns for each list, checkbox lists, sounds per event.
- Signed automatic updates from the author's server, from GitHub, from both or from a custom address.
