# 缺席、空值与失败（禁止空引用）

规格真相源：`specs/feature-tree/runtime/system-architecture-and-engineering-guide/absent-empty-failure-nullability/spec.md`，
设计归属 `DEC-025`。

## 四态模型（任何返回值只能落一态）

| 状态 | 含义 | 合法载体 |
|---|---|---|
| 在场有值 | 有这个值 | `T`、非空字符串、非空列表 |
| 在场为空 | 有这个字段，值是空的 | `""`、`[]`（业务合法值） |
| 缺席 | 没有这个值 | 契约 `NULLABLE`、Dart `T?`、JSON 省略键 |
| 失败 | 没做成 | `throw`、`RuntimeFailure`、`(T, error)`、领域 sealed |

**禁止跨态代偿**：失败不得编码为缺席或空值；缺席不得塌陷为空字符串或零值。

判定「失败」还是「缺席」只看一条：**用户预期的结果是否达成**。达成但无内容是在场为空或缺席；
未达成是失败。降级可达成的路径必须返回可用替代值并上报观测。

## 禁止（命中即 BLOCK）

- Dart：`catch` 之后 `return null` 当作结果，且不留任何证据。见下节的两条出路。
- Dart：用可空返回类型表达失败。`T?` 只允许表达缺席。
- Dart：`List<T>` 返回 null。非可空列表默认 `const []`。
- codegen：让必填字段在缺失时解码成功。必填缺失必须抛 `FormatException`。
- codegen：补入契约未声明的默认值。每一处解码期补值都必须能追溯到契约上的显式 `default`。
- codegen：对未声明可空性的字段自行推定可空。
- Go：HTTP wire 边界上值类型 `bool` 带 `omitempty`（`false` 会整个消失）。需要区分「未设置」
  与「false」时用 `*bool`，指针在这里恰好把三态表达对了。
- Go：出站列表序列化为 `null` 或因空而消失。
- Go：`domain` / `application` / 出站 DTO 用指针表达可选标量。
- Python：用 `None` 表示取到值之后的校验失败。

## catch 内 return null 的两条出路

不是所有 `catch` 内 `return null` 都在伪装失败。`jsonDecode` 抛异常，含义就是「这段输入不是
JSON」——没有任何动作没做成，null 是准确的。区别是语义的，静态分析读不出来，所以让代码
自己声明：

- **解析器**：异常本身就是形状判定（「这段输入不是一个 X」），函数用 **`try` 前缀命名**承诺
  该语义，对齐 `int.tryParse` 的生态惯例。叫 `_tryReadCoordinate` 就等于声明「返回 null
  表示这不是一个坐标」。
- **故障降级**：其余一律留证据——`ExceptionTelemetryPort.recordHandledException`、显式失败态，
  或 `developer.log(error:)`。观测基础设施自身（日志服务、遥测发件箱）不能自指上报，
  用 `developer.log`，它 release 下同样生效，不像 `kDebugMode` 那样让线上零证据。

```dart
// ✅ 解析器：名字承诺 null 的含义
Object? _tryDecodeJsonBody(String? body) {
  try { return jsonDecode(body!); } catch (_) { return null; }
}

// ✅ 故障降级：null 保留，但故障留痕
Future<Box<String>?> openStringBoxOrNull(String name) async {
  try {
    return await Hive.openBox<String>(name);
  } catch (error, stackTrace) {
    developer.log('open failed', name: '...', error: error, stackTrace: stackTrace);
    return null;
  }
}
```

## 必须

- 字段可空性只由对象契约声明：`fields.yaml` 的 `NOT_NULL` / `NULLABLE`、投影 `nullable`，
  或 wire schema 的 `required` / `default`；新增字段必须显式声明。
- 必填字段的 fail-closed 解码由 `local_contract` 锁定，生成器改动不得让它退化。
- Go 失败经 error 返回；领域端口的未命中用 sentinel 或 `AppError`，不用空返回兼作未命中信号。
- Go 指针只用于 `infrastructure` 的可空列与需要三态的写入面（change set 范式）。
- Python 的 `None` 只表示未命中；公开函数返回列表用 `[]`。
- 缺席优先以省略键表达；可空标量上 JSON `null` 与省略键等价。

## 门禁

```bash
make verify-app-null-failure-isolation
make verify-service-nil-semantics
```

两者已接入 `make gate` → `quwoquan_ops/gate/gate_repo.sh` 的 `run_app` / `run_cloud`。

- Dart 侧**无 allowlist 也无基线**：解析器约定与证据要求都能自动判定，没有可调的旋钮，
  新增只能是 BLOCK。
- Go 侧 wire 边界的 `bool` + `omitempty` 同样无基线（实测为 0）；领域端口 `return nil, nil`
  以棘轮承载，基线必须带 `_governance` 块并受 `verify_ratchet_baseline_governance.py` 约束。
