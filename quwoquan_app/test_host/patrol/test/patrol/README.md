# Ephemeral Patrol wrappers

`quwoquan_ops/cli/smoke/run_environment_patrol_smoke.py` 只在运行期间把
`quwoquan_app/test/user_acceptance/**` 的 canonical UAT 包装到本目录，并在退出时清理。
本目录不得保存业务测试副本。
