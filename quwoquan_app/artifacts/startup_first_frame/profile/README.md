# Startup profile artifacts

Place release `--trace-startup` / DevTools Timeline exports here after manual
profiling sessions. Each session should include:

- device profile and build mode
- Phase1 (`activity_on_create` → `flutter_engine_configured`) share
- Phase3 (`firstFrameMs` → `welcomeShownMs`) share
- link to the matching `startup_first_frame_report.json`

Automated probes write to `../probe*` directories; this folder is for human
profile evidence referenced by `cold-start-performance` acceptance.
