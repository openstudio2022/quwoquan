# release-operator

- **职责**：approved 对象原子发布到 canonical、创建 immutable release、
  `ship apply|rollback` 环境导入、服务 API 核验与 App UAT。
- **输入**：`5.review` 双审通过的对象、releaseId、目标环境。
- **输出**：canonical 增量、release、环境导入回执与 UAT 结果。
- **禁止**：修改 canonical 历史；dual-read 或旧路径 fallback；跳过幂等导入与回滚重放证据。
