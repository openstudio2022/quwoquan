# ops · design · python-script

- [MUST] 脚本角色、owner、入口与输出目录符合物理树职责。
  evidence: python-script-governance
- [MUST] 失败退出码、恢复动作与可重建输出单义。
  check: 读取 CLI terminal 与输出路径；判失败返回成功或输出不可重建时判失败。
- [MUST NOT] 建脚本 registry、inventory 或 orphan allowlist。
  check: 读取 diff；出现上述第二台账时判失败。
