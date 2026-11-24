# GitHub Accesible user guide

GitHub Accesible is a Windows application for working with all of GitHub and local git from the keyboard and with a screen reader (NVDA, JAWS or Narrator). This guide explains how to get started and how to use each part of the application. The full list of keys is in “Keyboard shortcuts” (Shift+F1).

## Getting started

### Installation

1. Download `GithubAccesible_vX.Y.Z.zip` from the GitHub releases or from the author's server.
2. Extract it to any folder you like.
3. Run `GithubAccesible.exe`.

The application is portable: everything it saves stays in its `data` folder. To uninstall it, delete the folder. To work with local repositories you need [Git for Windows](https://git-scm.com).

### Signing in

The first time you open the application, it asks whether you want to sign in. You can also do it from File, “Sign in with another account” (Ctrl+Shift+L). There are four ways to sign in:

- **With the browser and a code** (recommended). Press “Sign in”: the application copies an 8-character code, spells it out for you and opens the GitHub page in your browser. Paste the code there, press “Continue” and authorize the application. The window completes on its own. Your password, two-factor authentication or passkey are used on the web, never in the application.
- **With a personal access token**. Paste the token into its field. If you do not have one, the “Create a classic token on the web” and “Create a fine-grained token” buttons open GitHub with the permissions already checked.
- **Import the GitHub CLI session**, if you use `gh` on this computer.
- **Use Git's saved credentials** (Git Credential Manager).

For GitHub Enterprise Server, type your server's address in the “Server” field. You can have several accounts and switch between them with Ctrl+Shift+U. Tokens are stored encrypted with your Windows user account: if you copy the folder to another computer, you will have to sign in again.

Signing in with the browser works without any setup. If the token GitHub provides expires, the application renews it on its own. On GitHub Enterprise Server you need to register an OAuth app on the server itself and enter its identifier (Client ID) in Preferences, Accounts; the steps are in [Enable signing in with the browser](https://github.com/hxebolax/GithubAccesible/blob/main/docs/en/oauth.md).

### Language

The application is available in Spanish and English. The first time it opens, it uses the Windows language: Spanish if Windows is set to any variant of Spanish (Spain, Mexico, United States…) and English in any other case. You can change it in Preferences, General, “Interface language”: “Automatic (Windows language)”, “Español” or “English”. The new language takes effect after a restart; the application offers to restart right away.

The chosen language applies to everything: menus, messages, spoken messages, this guide (F1), the keyboard shortcuts and the what's new notes, both those shown after updating and those in the “Update available” window.

## You move the focus

Throughout the application, choosing something never moves you somewhere else. When you move through a list of sections, choose an option in a combo box (for example, “Search in” in the search window) or change a set of option buttons, what is shown to the right or below changes immediately, but the focus stays on the control you are on. You decide when to go to the content: with Tab, with Enter in section lists or with F6.

The focus only changes when you ask for it: when you open something (Enter, a section key such as Alt+1), when you press OK with a missing value (it goes to that field so you can fix it) or when a new window opens.

## The main window

On the left is the list of **sections**; on the right, the list with the content of the chosen section.

- When you move through the sections with the arrow keys, the section is shown on the right, but the focus **stays in the section list**. To go into the content, press Tab, Enter or F6.
- The section's keys that don't need a selected item also work from the section list: for example, Ctrl+Shift+A marks all notifications as read and Ctrl+N creates a new issue. Keys that act on an item (Delete, F2…) only work inside the list, where you can tell which one is selected; if you press them in the section list, the application explains this.
- F6 switches between the sections and the content.
- Alt+1 to Alt+9 and Alt+0 go straight to the first ten sections (and put the focus on their content).
- In Preferences, **Sections**, you can hide the ones you do not use and arrange them as you like, in this window and in repository windows; Alt plus a number follows that order.
- The **Actions** menu changes depending on the section and the selected item; it is the same menu that appears with the Applications key or Shift+F10 on an item.

Sections:

- **Home**: what the people and repositories you follow are doing.
- **Notifications**: Enter opens what triggered the notification (issue, pull request, Actions, release…) and marks it as read. Ctrl+L marks it as read, Delete marks it as done, Ctrl+Shift+S mutes the conversation and F4 switches between showing only unread notifications or all of them.
- **My repositories**, **Starred repositories** and **Watched repositories**: Enter opens the repository, Ctrl+K clones it, Ctrl+S stars or unstars it, Ctrl+N creates a repository and F4 changes the filter. Their actions also include “Download the code as zip”, “View wiki” and “View owner” (Ctrl+Shift+P). They show the name, description, visibility, language, stars and last update (and, in “My repositories”, the creation date); in Preferences, “List columns”, you can also add forks, open issues, default branch, type, creation date, size, license, topics, website, link, the HTTPS and SSH clone addresses, watchers, latest release and your permission. Watchers and the latest release are requested from GitHub separately, once per page, only when those columns are shown. The same applies to the repositories of an organization or a profile and to forks.
- **My issues** and **My pull requests**: F4 chooses what to show and their state. By default **My issues** shows the open issues **you created in any repository**, including other people's projects; F4 switches to the ones assigned to you, the ones that mention you, the ones you commented on, all the ones you are involved in or the ones in your repositories.
- **Gists**, **Organizations**, **Projects** and **Codespaces**.
- **Followers** and **Following**: besides the user name, they show their public repositories, their followers, how long they have been on GitHub, their contributions in the last year and the link to their profile; name and type can be added in Preferences, “List columns”. They load 30 at a time.
- **Local repositories**: git folders on this computer. Ctrl+N adds a folder and Ctrl+K clones a repository.
- **Search results**: the results of the last search (Ctrl+E).

Ctrl+U (view a profile) suggests the person in the selected row, already typed in: whoever did the activity, the person in the list, whoever wrote the issue or the commit, or the owner of the repository. Press Enter to open it or type another name over it.

### Background notifications

The application checks notifications on its own (every minute, or as often as GitHub asks). When a new one arrives, it announces it with speech and a sound, which is different if you are mentioned or asked for a review. The number of unread notifications appears next to the section. You can configure this in Preferences, Notifications (including a Windows notification and the system tray).

In the Notifications section, Ctrl+L marks the selected notification as read and Ctrl+Shift+A marks all of them as read. To hear the unread ones from any program, use the global hotkey Ctrl+Alt+Shift+N (see “Global hotkeys”).

Messages that arrive on their own (new notifications and the end of watched Actions runs) are read by the screen reader, which cuts them off as soon as you press a key. If you prefer to hear them in full while you type, go to Preferences, Notifications, “Read background messages with”, choose “A separate SAPI 5 voice” and, if you like, the voice, rate and volume; “Test the SAPI 5 voice” lets you hear it before you click OK. That voice may speak at the same time as the screen reader. Whatever you ask for with the keyboard (columns, Ctrl+H, Ctrl+Alt+Shift+N) is still read by the screen reader.

### The system tray

The application can keep running with its window hidden, with an icon next to the clock (Windows+B takes you to the system tray; the arrow keys, to the icon). File, “Hide to system tray”, hides it. In Preferences, General, you can choose:

- **Minimize to the system tray**: when minimized, the window hides in the system tray.
- **When closing the window, keep it in the system tray**: Alt+F4 or the Close button hide the window instead of exiting. To really exit: File, Exit (Ctrl+Q) or “Exit” in the icon's menu.
- **Start hidden in the system tray**.
- **Always show the system tray icon**: the icon also stays while the window is visible.

The icon's text says how many unread notifications there are. Enter or a click shows the window; the Applications key opens its menu: hide or show the window, go to notifications, read the unread notifications aloud, check now, search GitHub, Preferences and Exit.

### Global hotkeys

They work from any program, even when the application is in the system tray. By default:

- **Ctrl+Alt+Shift+G**: show or hide the application. If it is visible and in front, it hides it in the system tray; otherwise, it brings it to the front.
- **Ctrl+Alt+Shift+N**: say how many unread notifications there are and read the three most recent ones, without leaving what you are doing.

In Preferences, **Global hotkeys**, you can change these and turn on three more: open the Notifications section, search GitHub and check for new notifications now. In each field, press the combination you want (Ctrl, Alt or Windows, optionally with Shift, plus a letter, a number or F1 to F24) and the screen reader says it; Backspace or Delete clear it. If another program already uses a combination, Windows does not allow it: the application tells you at startup or when you apply the changes, so you can choose another one. You can also turn them all off.

### Command palette

Ctrl+Shift+O, in any window, opens the **command palette**: type part of the name of what you want to do (“default”, “wiki”, “clone”) and the list shows the commands in that window that contain it, with their key and their menu, as well as the actions for the item selected in the list. Enter runs the command. It lets you find anything without going through the menus, and helps you learn their keys.

## Lists

All lists in the application work the same way:

- Up and Down Arrow: the screen reader reads the whole row.
- Left and Right Arrow: move through the columns of the row and read them one by one. Ctrl+1 to Ctrl+9 read that column directly.
- Enter opens the item. Applications or Shift+F10 shows all its actions with their keys.
- F5 refreshes. When you reach the end, more items load on their own; Ctrl+M requests them manually.
- Ctrl+F filters the list by a text and Ctrl+Shift+F removes the filter.
- Ctrl+C copies the row, Ctrl+Shift+C copies the link, Ctrl+B opens the item in the browser and Ctrl+I shows all its details in a text you can read at your own pace.
- Ctrl+J sorts the list by the column being read: the first time in ascending order, the second time in descending order and the third time back to the original order, the one GitHub returns. Ctrl+Shift+J (or Actions, “Sort the list”) chooses the column and the direction. With the mouse, just click the column header. Dates, numbers and sizes are sorted by their value, not by their text (in ascending order, “3 days ago” comes before “5 minutes ago”), numbers inside text too (“issue 2” before “issue 10”), and items without a value go to the end. Each list remembers its sort order. Only the items already loaded are sorted: if the list has more pages, load them first with Ctrl+M.

In Preferences, Accessibility, you choose what is spoken when you move through the columns (row number, column name and content). In Preferences, “List columns”, you choose for each list which columns are shown and in what order: this decides what the screen reader reads as you move through the rows, and in what order.

## Searching GitHub

Ctrl+E opens the search. Choose what to search for (repositories, code, issues and pull requests, users, commits, topics or labels) and type the text. It supports all of GitHub's search syntax; the “Qualifier examples” button explains it.

When you change what you are searching for, or choose a search from the history or from your saved searches, the filter tabs change, but the focus stays on the combo box: move through them with Tab whenever you like.

For repositories there is also a **guided search**: a category (popular with a minimum number of stars, most forked, updated since a date, not updated since a date, asking for help, Awesome lists, or a topic such as accessibility, screen reader, artificial intelligence, Arduino or Synology), the language and the license. The “Search history” keeps the latest searches so you can repeat them.

In the results list, Applications (or Shift+F10) shows what you can do with each result, depending on what it is:

- **View owner** (Ctrl+Shift+P): opens the profile of the person or organization that owns the repository, with their details, their repositories, who they follow and the Follow button. It is available for repositories and also for issues, pull requests, code, commits and discussions found.
- **View author**: the profile of whoever wrote the issue, the pull request, the discussion or the commit.
- **Go to repository** (Ctrl+Shift+R): opens the repository that an issue, a code file, a commit or a discussion belongs to.
- For repositories, also: clone (Ctrl+K), star or unstar (Ctrl+S), watch and fork.
- For people and organizations: **Follow or unfollow**, without opening the profile.

## Writing text: the editor

Issues, comments, pull request descriptions, reviews and release notes are all written in the same editor:

- The text is Markdown. F7 shows the formatted preview.
- Ctrl+Enter sends. If sending fails, the editor does not close and your text is still there.
- If you close the editor without sending, it asks whether you want to save what you wrote as a **draft**; when you write in the same place again, it offers it to you.
- Tab and Shift+Tab move to the next or previous control, as everywhere else in Windows. If you prefer Tab to type a tab character in the text, turn on Preferences, Editor, “The Tab key types a tab character in Markdown text”; you then move between controls with Ctrl+Tab.
- **Attach file** (Alt+F), in issues, pull requests, discussions and comments, adds text files, such as a `.log` file to show to the developer. You can choose several at once. For each one, it asks how to attach it:
  - **Inside the text, collapsed**: the content goes into a code block that GitHub shows as the file name and expands when clicked. You can review and change it in the editor before sending.
  - **As a secret gist, with its link**: the file is uploaded to a gist that does not appear in listings, and the text only contains its link. It is the only option if the file does not fit in the text (GitHub allows 65,536 characters). It needs the “gist” permission, which signing in with the browser already requests.

  Before attaching a log, check that it does not contain passwords, tokens or personal data: anyone who can see the issue will read it, and a secret gist can be opened by anyone who has the link. GitHub does not allow uploading images or other binary files from applications, only from its website: send the text and then open it in the browser (Ctrl+B) to drag the file there.
- **Translate when sending into** (in the editor and in “New issue”): write in your language and send in another, reviewing the translation first. See “Translator”.

## The diff viewer

The differences of a commit, a pull request or a local file are shown as a list in which each line is a row with its type (“Added”, “Removed”, “Unchanged”, “Hunk” or “File”), its line number and its text. When you reach an added or removed line, a different sound plays.

- F8 and Shift+F8: next and previous group of changes.
- Ctrl+F8 and Ctrl+Shift+F8: next and previous hunk.
- F7 and Shift+F7: next and previous file.
- Ctrl+G: go to a line by its number.
- Ctrl+T: view everything as text to read it continuously or copy it.
- Ctrl+C: copy the line.
- Ctrl+D: says what has changed within the added or removed line you are on, comparing it with the line it replaces or that replaces it (“changes “timeout=30” to “timeout=60””, “adds…”, “removes…” or “Line rewritten”). If it has no matching line, it says so.
- Ctrl+Shift+D: diff summary (files, changes, and lines added and removed), the file you are in (new, deleted, renamed or modified) and the change number. F8 and Shift+F8 also say “Change n of m”.
- Ctrl+Shift+T: the narrated diff, a text that starts with the summary and goes through each change with its line numbers (“Changed line 12: … To: …”).
- Characters that cannot be seen (control characters, special spaces, marks that change the text direction) are shown with their name, such as “<U+202E RIGHT-TO-LEFT OVERRIDE>”, and when you reach a line that contains them you hear “Contains invisible characters”. They can hide malicious code, which is why it is worth knowing.
- In a pull request, Enter comments on the line and Ctrl+Enter reads the comments it already has (commented lines have an alert sound and a “Comments” column).

## The repository window

It opens with Enter on any repository, with Ctrl+O by typing “owner/name” or a link, or from a notification. Like the main window, it has the sections on the left and their content on the right (F6 switches between them, Ctrl+Tab changes section, Ctrl+W closes the window; Escape does not close it, so you do not lose your place).

Sections: Overview (information and a button to read the README with formatting), Code (folder and file browser, with Backspace to go up, F4 to switch branch and Ctrl+P to find a file), Issues, Pull requests, Discussions, Actions, Releases, Branches, Git tags, Commits, Projects, Wiki, Milestones, Issue labels, Collaborators, Forks, Stargazers, Security, Environments, Actions secrets and variables, Webhooks, Deploy keys, Rules and protection, Statistics, Deployments, Pages and Settings.

In all section lists: Enter opens, Ctrl+N creates, F2 changes or renames, Delete deletes (it always asks first) and F4 changes the filter (for example, open, closed or all issues, by label or assignee). To delete the whole repository, you have to type its name, as on the website.

In the Repository menu, **View owner** (Ctrl+Shift+P) opens the profile of the repository's owner, so you can see their other repositories or follow them. **Download the code as zip** saves the default branch to a zip file with the download manager (see “Downloads”). If the repository is a fork, **Open original repository** goes to the project it was copied from, and **Sync with the original** brings what is new in the original into one of your branches, like the “Sync fork” button on the website; in other repositories these two commands appear as unavailable.

In the Code section, “Download repository as ZIP” saves the code of the chosen branch to a zip file without needing git.

### The wiki

The **Wiki** section shows the pages of the repository's wiki: first the home page (Home), then the others in alphabetical order, and finally the sidebar and footer, if it has them. GitHub does not provide the wiki through its API: the application downloads it with git (Git for Windows is required) to `data/cache/wikis` and updates it every time you enter the section or press F5.

- Enter opens the page with formatting in the viewer. Links to other pages in the same wiki also open in the viewer; all others open in the browser.
- F2 edits the page in the editor (with preview and drafts) and Ctrl+N creates a new one, in Markdown or in another of the formats GitHub supports. Each change is saved to GitHub immediately, with the message you write or an automatic one. If you do not have permission to edit the wiki, you are told and nothing is changed.
- “Change title” renames the page and Delete deletes it (it asks first; the page remains in the history).
- “Page history” lists its changes: you can read the page as it was at any of them or view its differences in the diff viewer.
- Ctrl+P searches for a text in all pages and opens the one you choose.
- Ctrl+B opens the page in the browser and Ctrl+Shift+C copies its link.
- “Clone wiki to a folder” downloads it with git so you can work with it like any other repository.

If the wiki is disabled, the list label says so and the actions offer to enable it (if the repository is yours). If it is enabled but empty, GitHub does not create it until the first page is saved from the website: use “Create first page in browser” and then F5.

## Issues and pull requests

The issue window shows a summary at the top (title, state, author, labels, assignees, milestone, reactions and dates), then the **conversation** as a list (description, comments and events such as “labeled” or “closed”) and below it the full text of the focused item, which changes as you move without taking the focus away from the list. From the list you can comment (Ctrl+N), reply with a quote (Ctrl+R), edit or delete one of your own comments, react (Ctrl+E) and view it with formatting (Enter). From the Actions menu: close as completed or not planned, reopen, labels, assignees, milestone, lock, pin, transfer and subscribe.

**New issue** (Ctrl+N in a repository's Issues section): if the repository has templates, you choose one from the list, with its name and description. “Blank issue” only appears if the repository allows it, and its contact links (forums, security advisories) open in the browser.

- Text templates open the editor with their title and content.
- **Forms** ask for each piece of information in its own field: text, long text, combo box, checkbox list or checkboxes. Required fields say “(required)” and Ctrl+H reads the help for each field. Ctrl+Enter creates the issue and F7 shows the preview; if something required is missing, you are told what it is and the cursor goes to that field. The issue ends up exactly as if it had been filled in on the website.
- The issue is created with the labels, assignees and type that the template specifies; if GitHub does not accept them because of missing permissions, it is created without them and you are told.

When you create a **pull request** (from the repository or from the git window), the description starts with the repository's template; if there are several, you choose one or none.

The pull request window has tabs (Ctrl+Tab):

- **Conversation**: as in issues.
- **Commits**: Enter opens the differences of each commit.
- **Files changed**: the files and the diff viewer with the whole pull request. Enter on a line comments on it; comments can be saved in a pending review and submitted at the end.
- **Checks**: the result of each check; Enter opens the Actions run.
- **Review threads**: resolve, reopen, reply and go to the line.

“Review” (Alt+V) approves, requests changes or comments. “Merge” (Alt+M) allows a merge, squash or rebase and warns you if there are conflicts or missing checks. You can also enable auto-merge, mark as ready or as draft, request a review, update the branch and check it out in a local repository.

## Files, commits and blame

The file viewer shows a file in a read-only field: Ctrl+G goes to a line, Ctrl+L says which line you are on, Ctrl+F searches and F3 repeats the search. “Blame” shows in a list who changed each line and when; “History”, the commits of the file. “Edit” (Ctrl+E) opens the file so you can change it and save it with a commit, on the same branch or on a new one (with the option to open a pull request).

## GitHub Actions

The run window shows the information, the list of **jobs**, the list of **steps** of the chosen job and its clean **log** (without color codes; timestamps can be shown with a checkbox). In the log, F8 jumps to the next error or warning and reads it. Enter on a step takes you to its part of the log. There are lists of annotations and artifacts (Enter downloads). You can re-run everything or only the failed jobs (Ctrl+R and Ctrl+Shift+R), cancel, approve deployments and “Follow live”: while the run is in progress it refreshes every 10 seconds, announces changes and plays a success or failure sound when it finishes.

“Run workflow” (in the repository's Actions section) reads the workflow inputs and shows a control for each one.

### Watching runs in the background

The application can notify you when a run finishes even if you have no window open: it says the result (“Actions in ana/project: “CI” on main has finished: failed”), plays the success or failure sound and, if you want, shows a Windows notification.

- In a repository's Actions section, “Notify me when it finishes” (Ctrl+Shift+W) on a run in progress. It is also in the Run menu of its window.
- In the Repository menu, “Notify when each Actions run finishes” (checkbox) watches all runs of that repository until you uncheck it.
- When you push changes to GitHub from the git window, the runs triggered by that commit are watched automatically and you are told how they went. If the repository has no Actions, nothing is said.
- Tools, “Watched Actions runs”, shows what is being watched and lets you stop watching it.

What is being watched is remembered when you close the application. In Preferences, Actions, you choose for everything that is watched at once:

- Which runs to report: all of them, only the ones that fail (including canceled runs or runs that don't finish successfully) or only the ones that succeed.
- Whether the success or failure sound plays.
- Whether the result is announced by voice (by the screen reader or the SAPI 5 voice, depending on Preferences, Notifications).
- Whether a Windows notification is also shown.
- How often GitHub is checked and whether the runs triggered by each push are watched.

## Releases, gists, discussions and projects

- **Releases**: create (with automatically generated notes), edit, delete, upload assets and download them with the download manager (they continue even if you close the window). When you download an asset, if GitHub publishes its SHA-256 checksum, the application checks it on its own and tells you whether it is correct; if it does not match, the download ends with an error because the file is damaged. “Copy SHA-256 checksum” copies it so you can share it.
- **Gists**: view each file, edit it, add, rename or delete files, comments, history, star and fork.
- **Discussions**: comments with their replies, mark the answer, vote, close and reopen.
- **Profiles**: Ctrl+U, “View owner” or “View author” open a person's profile. It has tabs for Overview (details, pinned items and contributions), Repositories, Starred, Activity (what they have done, as in Home: GitHub only provides the events from the last 30 days, so when you reach the end, their earlier contributions keep loading year by year, back to when they joined GitHub, namely commits, opened issues and pull requests, reviews and created repositories; each year uses 1 point of the 5,000 per hour that GitHub allows, and this can be turned off in Preferences, Lists), Followers, Following, Gists and Organizations. The **Read profile README** button (Alt+M) opens, with formatting, the introduction shown on the website. If it is an organization, its own window opens.
- **Projects**: the items as a list, with a column for each field. “Move to” (Ctrl+M) changes the status without dragging anything; F2 changes any field; you can add drafts and issues, archive, filter and group.

## Local git

From “Local repositories” or with Ctrl+Shift+G, you open the window for a repository on this computer. Its status area shows the branch, whether it is ahead of or behind the remote, and how many changes there are. As in the other windows, moving through the section list shows each section without moving the focus; Enter, Tab or F6 go into its content. Sections:

- **Changes**: modified files; Space or Enter stages or unstages them, Ctrl+D shows their differences. Below is the commit message, with checkboxes to amend the last commit and to sign; Ctrl+Enter commits.
- **History**, **Branches**, **Tags**, **Stash**, **Remotes**, **Submodules**, **Worktrees** and **Reflog**.
- **Conflicts**: after a merge or rebase with conflicts, Enter on a file opens **block-by-block** resolution: each block is read out (“Block 2 of 5. Your version… The other version…”) and you choose with a button. In a rebase the sides are reversed, and the application tells you so clearly. Afterwards, you continue or abort the operation.

The Git menu fetches, pulls, pushes and syncs with spoken progress (only at milestones, so as not to overwhelm you) and with Cancel. If the remote is on GitHub, it also opens the repository in the application and creates pull requests.

## Downloads

Everything the application downloads (release assets, Actions artifacts and logs, code as zip) goes to the **download manager**. Downloads belong to the application, not to the window that started them: you can close the release window and keep doing other things while they download, several at a time.

- Open it with **Ctrl+Shift+D** from the main window, a repository window, the git window or any detail window (except the diff viewer, where that key gives the summary), from Tools, “Downloads”, from the system tray icon menu, or with a global hotkey if you set one.
- The **downloads list** shows, newest first, the name, the status (queued, downloading, paused, completed, error or canceled), the progress, how much has been downloaded and the total, the speed, the time left, where it comes from, the folder and, if it failed, the error explained. Rows update on their own without announcing every change: moving through the list gives you the current progress, and Ctrl+D says it.
- **Space** (or “Pause” and “Resume”) pauses the selected download, keeping what has been downloaded, and resumes it where it left off. A failed one is retried the same way, also from where it stopped.
- **Enter** opens the finished file (if it hasn't finished, it pauses or resumes). **Ctrl+O** opens the folder with the selected file.
- **Delete** cancels a download (it asks first and deletes what was downloaded) or removes a finished one from the list; the downloaded file is never deleted when you remove it from the list. “Remove completed” clears all completed and canceled downloads at once; “Pause all” and “Resume all paused” act on all of them.
- When each download finishes, a sound plays and you are told, even if the window is closed; if it fails, you are told why. For release assets, if GitHub publishes their SHA-256 checksum, it is checked automatically: if it doesn't match, the download ends with an error and the damaged file is not kept.
- If you exit the application with downloads in progress, you are asked first; they are paused, keeping what was downloaded, and continue on their own the next time you open it.

In Preferences, **Downloads**, you choose how many download at the same time (3 by default; the rest wait in the queue), whether unfinished downloads continue when the application opens, and whether the “Downloads” window opens every time one starts. The folder where they are saved is in Preferences, General.

## Translator

To read what other people write in another language, and to write in yours and send in another. Only what you ask for is translated (never the interface), always in the background.

- **Reading translated**: in the conversation of an issue or pull request, **Ctrl+T** translates the selected item and **Ctrl+Shift+T** the whole conversation at once, each part with its author. The same works in a discussion (also from the context menu). The “Translator” window opens with the text already translated into your reading language (by default, the interface language).
- **The “Translator” window** (Tools, “Translator”, Ctrl+Shift+Y): original text, source language (“Detect language” or a specific one), target language, engine and the translated text. Ctrl+Enter translates; “Swap languages” turns everything around so you can reply; “Copy translation” and “View formatted” (as a page, with headings and links); Escape closes it.
- **Writing in another language**: the editor and the “New issue” form have **“Translate when sending into”**. Write in your language, choose the language it will be sent in (more than a hundred) and press Send: the title and text are translated and shown to you in “Review the translation before sending”, where you can correct them. Nothing is sent until you press “Send the translation”; “Go back and edit” sends nothing. You can add the original, collapsed, at the end in case the translation is unclear. The last language you chose is remembered.
- Code blocks (```), links, @mentions and #references are not translated.

**Engines** (Preferences, Translation):

- **Google Translate**, the default: free and without a key. It is not an official API: after many translations in a row, Google may stop responding for a while; the application politely waits and retries and, if that fails, explains it.
- **MyMemory**: free and without a key, with a daily limit (about 5,000 characters; 50,000 if you enter an email in Preferences, Translation keys).
- **LibreTranslate**: open source; on your own server or on libretranslate.com with a key.
- With your own key: **Google Translate (Google Cloud Translation, official)**, **Microsoft Translator**, **DeepL** (the free key works), and the AI models **Gemini** (has a free tier), **ChatGPT** (OpenAI or any compatible service), **DeepSeek** and **Claude**, which translate more naturally. The cheapest model of each is used by default, and you can change it.

If the chosen engine fails, the free ones are tried (Google, then MyMemory), unless you turn this off. Keys are entered in Preferences, “Translation keys”, and are stored encrypted with your Windows user account. “Test the chosen engine” checks right away whether an engine and its key work, without saving them.

## Tools

- **Translator** (Ctrl+Shift+Y): see “Translator”.
- **SSH and GPG keys**: the account's keys (add from a file or by pasting them, delete) and generate a new SSH key and upload it.
- **Git settings**: name, email, default branch, line endings, rebase when pulling, and signing.
- **API rate limit**, **GitHub status**, **Spoken message history**, log folder and diagnostic package.

## Preferences

Tools, Preferences (Ctrl+P). Changes are applied immediately in the open windows; Cancel saves nothing and “Restore defaults” goes back to the original settings.

- **General**: interface language, section shown at startup, speech at startup, system tray (minimize, close, start and always-visible icon), confirm before exiting, downloads folder.
- **Updates**: check at startup, and the source (author's server and GitHub, only one of them, or a custom address).
- **Accounts**: OAuth app identifier and the permissions requested.
- **Accessibility**: speech and braille messages, delay, column-by-column reading, announcement of checkbox lists (state, whether it comes before the text, position), help that the screen reader reads, diff viewer columns and their sounds, and HTML formatting.
  - **Help**: every control has a help text, the same one that Ctrl+H reads. The screen reader can also read it automatically when you reach the control. “Help: read it when focus reaches buttons and checkboxes” (on by default) reads it on buttons and standalone checkboxes. “Help: also read it on every row of checkbox lists” (off by default) repeats it on each row of a checkbox list, such as “Search text in” in the search window. If you turn it off, when you move through the list you only hear each row and whether it is checked. Ctrl+H always reads the help.
- **Sounds**: enable, mute, volume, sound pack and a list of every event to turn its sound on or off, with a button to test it.
- **Lists**: items per page, relative or full dates, and whether a profile's activity continues with earlier years (see “Profiles”).
- **Downloads**: how many at a time, continuing unfinished downloads when the application opens, and opening the “Downloads” window when one starts.
- **Notifications** (including who reads background messages: the screen reader or a SAPI 5 voice with its voice, rate and volume), **Global hotkeys** (see above), **Actions** (watching runs: which results to report, sound, voice and Windows notification; and timestamps in logs), **Git**, **Editor** (confirm before discarding, signature and whether Tab types tab characters), **Network and logging**.
- **Translation**: engine, the language to translate what you read into and from, the language to translate what you send into, adding the collapsed original, trying the free engines if the chosen one fails, and “Test the chosen engine”. **Translation keys**: the email for MyMemory, the LibreTranslate server, and the keys and models of the engines that need them (see “Translator”).
- **List columns**: visible columns and their order in each list.
- **Sections**: for the main window and for the repository window, which sections are shown (checkboxes) and in what order (Move up and Move down). “Search results” and “Overview” cannot be hidden. If you open a hidden section from somewhere else, you are told that it is hidden.

## Updates

The application checks for new versions at startup and once a day, and also from Help, “Check for updates”. When it finds one, it shows its what's new notes (those of all versions later than yours, in case you skipped any) and offers “Update now”, “Skip this version” or “Remind me later”. If the server does not provide them, it says so, and you will see them when the new version opens. After updating, the application opens the what's new notes once: those for the new version and at least those for the three previous ones. Every version is signed: if the package does not have the author's signature, it is rejected. Before replacing anything, a backup is made, your data in `data` is not touched and, if the new version does not start correctly, the application automatically goes back to the previous one.

## Troubleshooting

- **A section says you need to sign in**: sign in with Ctrl+Shift+L.
- **“The session is not valid or has expired”**: the token was revoked or has expired. Sign in again.
- **“The organization requires the token to be authorized for its single sign-on (SSO)”**: open the link in the message and authorize the token for that organization.
- **The request limit has been reached**: the message says what time it resets. Tools, “API rate limit” shows the details.
- **The screen reader repeats a long help text on every item**: turn off help in Preferences, Accessibility. You can always hear it with Ctrl+H.
- **I cannot attach an image or a ZIP file**: GitHub only allows uploading them from its website. Send the text, open it in the browser with Ctrl+B and drag the file there. Text files can be attached from the editor (Alt+F).
- **Git is not installed**: install Git for Windows or enter the path to `git.exe` in Preferences, Git.
- **Something goes wrong**: Tools, “Create a diagnostic package” creates a ZIP file with the logs, without tokens or your Windows user name, so you can ask for help.

## Data and privacy

Everything the application saves is in its `data` folder: settings (`config`), encrypted tokens (`config/secretos.dat`), drafts (`db`), logs (`logs`) and temporary files (`temp`). It sends nothing to anyone except GitHub (and the update server, to check for versions). Logs never contain tokens.

## Author and license

GitHub Accesible is the work of Héctor J. Benítez Corredera and is distributed under the GPL version 3 license. If you find it useful, you can buy the author a coffee from Help, “Buy me a coffee if you like my work”.
