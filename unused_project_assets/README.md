# Unused Project Assets

This folder isolates files that are not used by the current FDSM Articles runtime, frontend build, backend services, Docker images, or release package.

Current contents:

- `pretext-main/`: external `@chenglou/pretext` reference project.
- `pretext/`: local reference skill notes for that external project.
- `frontend-src-lib/pretextRichInline.js`: previously unused frontend bridge that imported `../../../pretext-main/src/rich-inline.ts`.

Code evidence before moving:

- `frontend/src/lib/pretextRichInline.js` was the only runtime-source reference to `pretext-main`.
- No backend, router, service, deploy script, Dockerfile, or current frontend entry imported `pretextRichInline.js`.
- `frontend/Dockerfile`, `.dockerignore`, and `deploy/create_release_package.ps1` already excluded `pretext-main` from production build/package paths.

Do not restore these files into runtime code unless the needed Pretext code is vendored into `frontend/src/lib/` or added as a real package dependency.
