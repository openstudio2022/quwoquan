Place the pinned `libwebrtc.zip` desktop archive here when desktop WebRTC builds are intentionally enabled.

This repository forbids `CMake` from downloading that archive during build time. If the file is absent, desktop plugin builds fail closed and require an explicit vendoring step.
