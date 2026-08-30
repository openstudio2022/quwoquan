# ops · dev · python-script

- [MUST] 稳定脚本位于合法角色目录并由唯一入口调用。
  evidence: python-script-governance
- [MUST] 缓存与运行输出只进入可删除、可重建目录。
  check: 读取输出路径；写入源码或删除后不可重建时判失败。
- [MUST NOT] 在源码树留下 bytecode/cache 或复制治理台账。
  check: 扫描 changed_paths 与源码树；命中 cache/registry/inventory 时判失败。
