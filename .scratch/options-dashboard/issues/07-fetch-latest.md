# 07: Fetch latest

**What to build:** A Fetch latest button pulls a new Deribit snapshot from the public API and the whole page switches to it, showing its capture time. A failed fetch keeps the previous snapshot and shows the error. Changing views, expiries, zoom or assumptions reuses the current snapshot.

**Blocked by:** 02

**Status:** ready-for-agent

- [ ] A fetched snapshot has the same shape and validation as the frozen one: every API response with its capture times, the index from the index request.
- [ ] The page shows the snapshot's capture time.
- [ ] A simulated fetch failure keeps the previous snapshot and shows the error (spec check 9).
- [ ] Interacting with any control does not fetch.
- [ ] Tests stay offline.
