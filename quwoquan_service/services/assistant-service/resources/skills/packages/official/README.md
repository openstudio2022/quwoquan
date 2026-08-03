# Official Skill Package assets

This directory contains immutable, content-addressed assets referenced by a
signed `SkillPackageRelease`. The assistant runtime never scans this tree; it
opens only the exact `skill-package://official/...` locators declared by the
currently active release and re-verifies every asset digest before use.

Release descriptors and signatures are produced by the controlled Skill
package publication pipeline. Signing private keys and credentials never live
in this repository.
