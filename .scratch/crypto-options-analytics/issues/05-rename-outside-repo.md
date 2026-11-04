# 05: Rename the repository, remote and folder

**What to build:** Outside the repository, everything follows the new name, in the order the spec gives: commit; rename the GitHub repository to `crypto-options-analytics`; point `origin` at the new URL; copy Claude's project memory folder to the new path; move the local folder; recreate the virtual environment there and run lint and tests. Done by Claude; moving the folder is the last step and ends sessions in the old path.

See `../spec.md` (Rename outside the repository).

**Blocked by:** 04

**Status:** resolved

- [x] The GitHub repository shows the new name and the old URL redirects.
- [x] `origin` fetches from the new URL.
- [x] Claude's memory is present at the new project path.
- [x] Lint and tests pass in the moved folder with a fresh environment.

## Comments

- 2026-11-04: Done by Claude. GitHub repository renamed (old URL returns 301 to the new one), `origin` fetches from https://github.com/KengThanabadee/crypto-options-analytics.git, memory copied to the new project path, folder moved to ~/Developer/crypto-options-analytics with a fresh conda environment at .venv; lint and tests pass there.
