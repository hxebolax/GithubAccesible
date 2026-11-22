# Enabling sign-in with the browser

Since version 1.0.1 the application includes the Client ID of the author's “Accesible para GitHub” OAuth app, so signing in with the browser works without any setup. This guide is for maintaining that OAuth app, using your own, or using GitHub Enterprise Server.

Signing in “with the browser and a code” uses GitHub's OAuth device flow. To work, it needs an OAuth app registered on GitHub and its public identifier (Client ID). This document explains how to register it, how to test it and how to build it into the application so that nobody has to configure anything.

The Client ID **is not secret**: the device flow does not use the client secret, so you do not need to generate it or store it. The Client ID can be written in the code and in the public repository.

## 1. Register the OAuth app (only once)

1. Sign in to GitHub in the browser and open <https://github.com/settings/applications/new>. This is the same as going to Settings, Developer settings, OAuth Apps and selecting “New OAuth App”.
   - If you prefer the OAuth app to belong to an organization, use `https://github.com/organizations/NAME/settings/applications/new`.
2. Fill in the form:
   - **Application name**: `Accesible para GitHub`. This is the name everyone will see on the authorization page. GitHub does not allow names that start with “GitHub” or “Gist” (in uppercase or lowercase), so neither “GitHub Accesible” nor “GithubAccesible” can be used.
   - **Homepage URL**: `https://github.com/hxebolax/GithubAccesible`.
   - **Application description** (optional): `Aplicación de escritorio accesible con lector de pantalla para manejar GitHub y git.`
   - **Redirect URI** (“Authorization callback URL” in older forms): `https://github.com/hxebolax/GithubAccesible`. The device flow does not use it, but GitHub requires it.
   - **Allow wildcard matching**: leave it unchecked.
   - **Enable Device Flow**: check it. Without this check box, GitHub responds with “device_flow_disabled” and signing in with the browser does not work.
   - **Expire user access tokens**: preferably leave it unchecked. If it is checked, the token expires after 8 hours and the application renews it automatically with the refresh token (which lasts 6 months if unused); this works, but leaving it unchecked means fewer things can go wrong.
3. Select “Register application”.
4. On the page that appears, copy the **Client ID** (it starts with `Ov23` or `Iv1.` and is about 20 characters long). Do not select “Generate a new client secret”: it is not needed.

If you forgot to check “Enable Device Flow”, go back to that page (Settings, Developer settings, OAuth Apps, Accesible para GitHub), check the box and select “Update application”.

Optionally, you can upload the application icon (`data/icons/app.ico` converted to PNG) under “Upload new logo”: it is shown on the authorization page.

## 2. Test it without building anything

1. Open GitHub Accesible, go to Tools, Preferences (Ctrl+P), **Accounts** tab.
2. Paste the Client ID into “OAuth app identifier (Client ID)” and select OK.
3. Open File, “Sign in with another account” (Ctrl+Shift+L), choose “With the browser and a code” and select “Sign in”.
4. The application copies the code, spells it out and opens <https://github.com/login/device>. Paste the code, select “Continue” and then “Authorize”.
5. The sign-in window completes by itself and the account appears in the status bar.

What you enter in Preferences takes priority over the value in the code, so you can also use it to test another OAuth app or GitHub Enterprise.

## 3. Build it into the application (for everyone)

1. In `app/services/github/autenticacion.py`, write the Client ID in `ID_CLIENTE_OAUTH`:

   ```python
   ID_CLIENTE_OAUTH = "Ov23xxxxxxxxxxxxxxxx"
   ```

2. Clear the field in Preferences, Accounts in your own installation to check that the value from the code is used.
3. Increase the version number (for example, 1.0.1) in `app/core/version.py` and `pyproject.toml`, and add something like this to `docs/changelog.md`: “You can now sign in with the browser and a code without any setup”.
4. Run the checks and publish:

   ```
   .venv\Scripts\python.exe -m pytest
   .venv\Scripts\python.exe tools\publicar.py
   ```

Existing installations will receive the new version through the updater, and signing in with the browser will work without changing anything.

## GitHub Enterprise Server

OAuth apps from github.com do not work on an enterprise server. If you use GitHub Enterprise Server, you must register your own OAuth app at `https://YOUR-SERVER/settings/applications/new` with the same details and the “Enable Device Flow” check box checked (the server administrator must have the device flow enabled), and enter its Client ID in Preferences, Accounts.

## If something goes wrong

- **“device_flow_disabled”**: “Enable Device Flow” is not checked in the OAuth app.
- **“incorrect_client_credentials”** or “Not Found”: the Client ID was copied incorrectly or belongs to another server.
- **The organization does not show its repositories**: if the organization restricts OAuth apps, select “Request” (or “Grant” if you are an owner) next to its name on the authorization page. You can also do this later in Settings, Applications, Authorized OAuth Apps, Accesible para GitHub.
- **The code expired**: it lasts 15 minutes. Select “Sign in” again.
