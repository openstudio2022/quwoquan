# Official Skill package source

This is the single source-controlled input root for the official Skill package
publisher and local contract tests. `SourceBuilder` compiles the manifests,
profiles, input schemas, prompts, presentation templates, and replay corpus in
this directory into signed immutable package assets.

The assistant runtime never scans this source tree. Runtime assets live under
[`../../skills/packages/official`](../../skills/packages/official/README.md) or
an environment-injected root with the same immutable release layout, and are
addressed only through the active or frozen `SkillPackageRelease` digest.

Do not copy, symlink, mirror, or fall back to another source root.
