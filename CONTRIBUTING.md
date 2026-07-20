# Contributing

Issues and pull requests are welcome. Please keep changes scoped, typed, tested, and safe for a
local simulator control system.

## Ground rules

- Do not commit BeamNG assets, maps, executables, logs containing personal paths, API keys, model
  weights, generated TensorRT engines, or per-install tokens.
- Do not add arbitrary eval/shell/file tools.
- Preserve loopback restrictions and confirmation gates.
- New direct-control features need watchdog/failure tests.
- New BeamNG/Lua API use needs a version note and local integration evidence.
- New model backends must load lazily, document weight licensing, and remain outside imports/tests
  when their extras are absent.

## Workflow

1. Create a focused branch.
2. Add or update tests before changing a protocol/safety behavior.
3. Run the checks in `docs/DEVELOPMENT.md`.
4. Describe simulator versions and any skipped live checks in the pull request.

By contributing, you agree that your contribution is licensed under the repository's MIT License.

