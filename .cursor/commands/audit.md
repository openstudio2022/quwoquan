---
name: /audit
id: audit
category: Quality
description: 端云全栈一致性审计（语义 + 结构 + metadata + ArchUnit，代码库级健康度检查）
---

执行全栈一致性审计，覆盖端侧语义审计 + 云侧结构约束 + metadata↔代码同步 + 特性树一致性。

**与 `/verify` 的关系**：
- `/verify`：**特性级**，检测某一特性实现与基线的漂移（spec/design/acceptance drift）
- `/audit`：**代码库级**，检测整体代码结构的健康度（DDD、metadata、语义、特性树）
- 两者互补，可在 `/verify` 中追加 `--with-audit` 选项联合运行

---

## 执行范围

```
┌────────────────────────────────────────────┐
│ 1. 端侧语义审计 (quwoquan_app)              │
│    - Flutter analyze                        │
│    - 硬编码视觉字面量检查                    │
│    - cloud/ 生成代码一致性检查               │
├────────────────────────────────────────────┤
│ 2. 云侧结构约束 (quwoquan_service)          │
│    - DDD 层级导入方向检查                    │
│    - 禁止直接数据库驱动导入                  │
│    - runtime 统一能力使用检查                │
│    - codegen 产物完整性检查                  │
├────────────────────────────────────────────┤
│ 3. metadata↔代码同步 (端云共同)              │
│    - Go struct ↔ fields.yaml               │
│    - Dart DTO ↔ fields.yaml                │
│    - OpenAPI ↔ service.yaml + fields.yaml  │
│    - Migration ↔ storage.yaml              │
├────────────────────────────────────────────┤
│ 4. 特性树一致性                             │
│    - 四类文档：spec/design/tasks/acceptance  │
│    - tree_index.yaml ↔ 目录结构             │
│    - acceptance.yaml 完整性                 │
└────────────────────────────────────────────┘
```

---

## 1) 端侧语义审计

在 `quwoquan_app/` 下执行：

**1.1 Flutter 静态分析**

```bash
cd quwoquan_app && flutter analyze
```

**1.2 硬编码视觉字面量检查**

```bash
cd quwoquan_app && python3 - <<'PY'
import pathlib, re

targets = list(pathlib.Path("lib").rglob("*.dart"))
pattern = re.compile(
    r"fontSize:\s*\d+(\.\d+)?(\.sp)?|"
    r"size:\s*\d+(\.\d+)?(\.sp)?|"
    r"BorderRadius\.circular\(\s*\d+(\.\d+)?\s*\)|"
    r"EdgeInsets\.(all|symmetric|only)\(\s*\d+"
)
found = False
for p in targets:
    for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
        if pattern.search(line):
            if "DO NOT EDIT" not in p.read_text(encoding="utf-8")[:200]:
                print(f"{p}:{i}: {line.strip()}")
                found = True
if not found:
    print("✓ No hardcoded visual literals found.")
PY
```

**1.3 cloud/ 生成代码一致性**

```bash
cd quwoquan_app && find lib/cloud/models -name "*.dart" -exec grep -L "DO NOT EDIT" {} \;
```

---

## 2) 云侧结构约束（ArchUnit-like）

在 `quwoquan_service/` 下执行：

**2.1 DDD 层级导入方向**

```bash
cd quwoquan_service && python3 - <<'PY'
import pathlib, re

violations = []
for svc in pathlib.Path("services").iterdir():
    if not svc.is_dir():
        continue
    domain_dir = svc / "internal" / "domain"
    app_dir = svc / "internal" / "application"
    if not domain_dir.exists():
        continue

    forbidden_in_domain = ["internal/infrastructure", "internal/adapters", "internal/application",
                           "go.mongodb.org", "github.com/jackc/pgx", "github.com/go-redis"]
    forbidden_in_app = ["internal/infrastructure", "internal/adapters",
                        "go.mongodb.org", "github.com/jackc/pgx", "github.com/go-redis"]

    for go_file in domain_dir.rglob("*.go"):
        content = go_file.read_text(encoding="utf-8")
        for forbidden in forbidden_in_domain:
            if forbidden in content:
                violations.append(f"DOMAIN_VIOLATION: {go_file} imports {forbidden}")

    if app_dir.exists():
        for go_file in app_dir.rglob("*.go"):
            content = go_file.read_text(encoding="utf-8")
            for forbidden in forbidden_in_app:
                if forbidden in content:
                    violations.append(f"APP_VIOLATION: {go_file} imports {forbidden}")

if violations:
    for v in violations:
        print(f"✗ {v}")
else:
    print("✓ DDD layer import constraints: PASS")
PY
```

**2.2 禁止绕过 runtime 统一能力**

```bash
cd quwoquan_service && python3 - <<'PY'
import pathlib

violations = []
for svc in pathlib.Path("services").iterdir():
    if not svc.is_dir():
        continue
    for go_file in (svc / "internal").rglob("*.go") if (svc / "internal").exists() else []:
        if "/infrastructure/" in str(go_file) or "/tests/" in str(go_file):
            continue
        content = go_file.read_text(encoding="utf-8")
        if "go.mongodb.org/mongo-driver" in content:
            violations.append(f"DIRECT_MONGO: {go_file}")
        if "github.com/jackc/pgx" in content:
            violations.append(f"DIRECT_PGX: {go_file}")
        if "database/sql" in content:
            violations.append(f"DIRECT_SQL: {go_file}")

if violations:
    for v in violations:
        print(f"✗ {v}")
else:
    print("✓ No direct database driver imports outside infrastructure: PASS")
PY
```

---

## 3) metadata↔代码同步

```bash
cd quwoquan_service && make verify
```

---

## 4) 特性树一致性

```bash
cd /path/to/quwoquan && bash agent_ops/scaffold/verify_feature_tree_refactor.sh
```

---

## 输出格式

```
╔══════════════════════════════════════════╗
║         全栈审计报告（/audit）            ║
╠══════════════════════════════════════════╣
║ 1. 端侧语义审计                          ║
║    Flutter analyze:     ✓ PASS / ✗ FAIL ║
║    硬编码字面量:         ✓ PASS / ✗ FAIL ║
║    cloud/ 生成代码:      ✓ PASS / ✗ FAIL ║
║ 2. 云侧结构约束                          ║
║    DDD 层级导入:         ✓ PASS / ✗ FAIL ║
║    数据库驱动隔离:       ✓ PASS / ✗ FAIL ║
║    runtime 统一能力:     ✓ PASS / ✗ FAIL ║
║ 3. metadata↔代码同步                     ║
║    make verify:          ✓ PASS / ✗ FAIL ║
║ 4. 特性树一致性                          ║
║    tree ↔ 目录:          ✓ PASS / ✗ FAIL ║
╚══════════════════════════════════════════╝
```

若有 FAIL 项，输出每个违规的 `文件:行号` + 违反规则 + 修复建议。

---

## 5) 推荐系统合规审计（与 `/rec-audit` D9/D10 对齐）

推荐域代码的 DDD / 强类型 / 存储无关 / 端云一致扫描：

```bash
cd quwoquan_service && python3 -c "
import pathlib
violations = []
for d in ['runtime/recommendation', 'runtime/observability']:
    p = pathlib.Path(d)
    if not p.exists(): continue
    for f in p.rglob('*.go'):
        c = f.read_text()
        for b in ['go.mongodb.org', 'github.com/go-redis', 'database/sql']:
            if b in c: violations.append(f'DDD: {f} imports {b}')
for v in violations: print(f'✗ {v}')
if not violations: print('✓ DDD recommendation/observability layers: PASS')
"
```

特征端云一致性：

```bash
cd quwoquan_service && python3 scripts/ml/verify_feature_consistency.py
```

---

## 6) 可观测与埋点审计（与 `/obs-audit` D8/D9 对齐）

页面行为埋点覆盖率扫描（内容核心路径是否接入 Tracker）：

```bash
cd quwoquan_app && python3 -c "
import pathlib, re
pages = list(pathlib.Path('lib/ui').rglob('*_page.dart'))
tracked = 0
for p in pages:
    c = p.read_text()
    if 'ContentEngagementTracker' in c or 'ContentBehaviorTracker' in c or 'TelemetryService' in c:
        tracked += 1
print(f'页面埋点覆盖: {tracked}/{len(pages)}')
if tracked < len(pages) * 0.5:
    print('⚠ 覆盖率低于 50%，建议执行 /obs-plan')
"
```

---

## 输出格式

```
╔══════════════════════════════════════════╗
║         全栈审计报告（/audit）            ║
╠══════════════════════════════════════════╣
║ 1. 端侧语义审计                          ║
║    Flutter analyze:     ✓ PASS / ✗ FAIL ║
║    硬编码字面量:         ✓ PASS / ✗ FAIL ║
║    cloud/ 生成代码:      ✓ PASS / ✗ FAIL ║
║ 2. 云侧结构约束                          ║
║    DDD 层级导入:         ✓ PASS / ✗ FAIL ║
║    数据库驱动隔离:       ✓ PASS / ✗ FAIL ║
║    runtime 统一能力:     ✓ PASS / ✗ FAIL ║
║ 3. metadata↔代码同步                     ║
║    make verify:          ✓ PASS / ✗ FAIL ║
║ 4. 特性树一致性                          ║
║    tree ↔ 目录:          ✓ PASS / ✗ FAIL ║
║ 5. 推荐系统合规                          ║
║    DDD/端云/特征一致:    ✓ PASS / ✗ FAIL ║
║ 6. 可观测与埋点                          ║
║    页面埋点覆盖:         N/M (xx%)       ║
╚══════════════════════════════════════════╝
```

若有 FAIL 项，输出每个违规的 `文件:行号` + 违反规则 + 修复建议。

---

## 与其他命令的关系

| 命令 | 视角 | 触发时机 |
|------|------|---------|
| `/verify` | **特性级**：spec↔实现漂移检测 | dev 完成后、commit 前 |
| `/audit` | **代码库级**：结构健康度检查 | 任意时刻、周期检查 |
| `/obs-audit` | **可观测专项**：埋点/存储/性能/指标 | 可观测体系评估时 |
| `/rec-audit` | **推荐专项**：行为/特征/召回/排序 | 推荐系统评估时 |
| `/verify --with-audit` | 两者联合运行 | 需要完整质量报告时 |
