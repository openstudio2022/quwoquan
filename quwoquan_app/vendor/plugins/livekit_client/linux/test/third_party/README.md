Vendored test-only third-party sources for the Linux `livekit_client` plugin belong under this directory.

When Linux plugin unit tests are intentionally enabled, stage a local `googletest/` checkout here first. The plugin `CMakeLists.txt` no longer fetches GoogleTest from the network during test configuration.
