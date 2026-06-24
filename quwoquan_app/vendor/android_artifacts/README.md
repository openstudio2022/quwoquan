## Vendored Android Artifacts

These pinned AARs are committed so supported app builds do not fetch GitHub or custom Maven artifacts at compile time.

- `android-144.7559.01.aar`
  - source coordinate: `io.github.webrtc-sdk:android:144.7559.01`
  - sha256: `9e2ba6fd25fd993772d71679183ecd75ea95705962ee506612756d88d93249d8`
- `audioswitch-89582c47c9a04c62f90aa5e57251af4800a62c9a.aar`
  - source coordinate: `com.github.davidliu:audioswitch:89582c47c9a04c62f90aa5e57251af4800a62c9a`
  - sha256: `a5e233afbfc60954401f4f9e3a170ddecbcd39738fffbbebe71865ec54801443`
- `noise-2.0.0.aar`
  - source coordinate: `io.livekit:noise:2.0.0`
  - sha256: `de84ec504e0d7371bcb2ae3790573b418a3b4f3a4b1af63b91ab991e81169575`

Upgrade policy:

- Do not replace these artifacts implicitly during build, test, or launch.
- When a dependency upgrade is intentional, update the plugin manifest, replace the vendored AAR in this directory, refresh the SHA record above, and rerun the dependency purity gate.
