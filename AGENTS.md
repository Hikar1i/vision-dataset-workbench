# Repository Instructions

## Documentation Boundary

- The root `README.md` is the project entry point. Curated, long-term documentation about the current implemented system lives in `project-docs/` and is tracked by Git.
- The root `docs` path is a tracked compatibility symlink to `.ai-local/scratch-docs/`; it is not the project documentation directory.
- Brainstorming designs, validated specs, implementation plans, investigations, handoffs, and other AI work products remain local even after approval or completion. Write them under `docs/` or `.ai-local/scratch-docs/`, never under `project-docs/`, and do not commit their contents.
- Do not create a new file in `project-docs/` unless the user explicitly requests a new long-term project document. When implementation changes documented behavior, update the matching existing document.
