# Moving SkyForge into its own repository

SkyForge was developed in an environment whose GitHub token **cannot create new
repositories** (`403 Resource not accessible by integration`). To keep the work
safe it was pushed to a branch of an existing repo:

- **Source:** `arancool3000/EmberAI`, branch **`claude/wizardly-mayer-3uf96k`**
- It is a single, self-contained commit with unrelated history to EmberAI's
  `main`, so it lifts out cleanly.

## Option A — spin it out yourself (no extra permissions)

```bash
# 1) Create an EMPTY repo named "skyforge" at https://github.com/new
#    (do NOT add a README, .gitignore, or license)

# 2) Clone just this branch, repoint it at the new repo, push as main:
git clone --single-branch --branch claude/wizardly-mayer-3uf96k \
  https://github.com/arancool3000/EmberAI.git skyforge
cd skyforge
git remote set-url origin https://github.com/arancool3000/skyforge.git
git push -u origin claude/wizardly-mayer-3uf96k:main
```

You now have a clean standalone `skyforge` repo with `main` containing only this
project. Delete the temporary branch from EmberAI when you're done:

```bash
git push https://github.com/arancool3000/EmberAI.git --delete claude/wizardly-mayer-3uf96k
```

## Option B — let me push it for you

Create the empty `skyforge` repo at https://github.com/new and tell me it
exists; I'll push the code to it as `main`.

## Run it after cloning

```bash
npm install
npm run dev      # open the printed http://localhost:5173 URL
```
