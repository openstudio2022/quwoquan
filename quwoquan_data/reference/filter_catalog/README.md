# FilterCatalogRelease canonical artifact

本目录是滤镜目录的数据工程发布入口。唯一可编辑业务数据是
`releases/<releaseId>/filter_catalog_release.json`；App bootstrap、
四环境 immutable-release import manifest 与 `bootstrap_binding.json` 都由 `qwq-data`
从该 artifact 生成，不是第二真相源。

## CLI

```bash
# 从已有 canonical release 重生全部派生物
python3 -B quwoquan_data/scripts/cli.py filter-catalog materialize \
  --release-id <releaseId>

# 只读校验
python3 -B quwoquan_data/scripts/cli.py filter-catalog validate
```

`materialize` 会更新唯一 bootstrap binding、App replica，以及四环境对同一
immutable release 的 import 输入。Alpha/Beta/Gamma 采用 Stage 后 Activate，
Prod 只声明 Stage 与受保护的灰度 Activate；任何环境都不使用 test fixture、
`seedRefs` 或直接存储写入。

## Canonical digest

算法标识固定为 `sha256:qwq-filter-catalog-canonical-json`：

1. 摘要投影只含 `categories`、`presets`、
   `recommendedFallbackPresetIds`；排除 `releaseId`、`sourceOwner` 和
   `canonicalDigest`。
2. `categories` 按 `(sort, categoryId)` 排序；`presets` 按
   `(categoryId, sort, presetId)` 排序；推荐列表保留声明顺序。
3. 每个 object 的 key 按 Unicode scalar value 升序；array 不做上述规则之外的重排。
4. string 使用 UTF-8 JSON 字符串，只执行 JSON 必需转义；非 ASCII 字符不转义，
   不做 Unicode normalization。
5. number 按十进制词法处理：禁止 NaN/Infinity；不用指数；去掉无意义的尾随零和
   小数点；所有正负零编码为 `0`。
6. `null`、boolean 使用 JSON 小写字面量；成员间不写空白，末尾不写换行。
7. 对上述 UTF-8 bytes 计算 SHA-256，输出 64 位小写 hex。

该规则不依赖 Python 的二进制 `float`，Go 可用 `math/big` 或十进制词法实现，
Dart 可用 `BigInt` 加十进制字符串实现。跨语言固定向量位于
`digest_test_vector.json`；其中 `canonicalJsonUtf8` 是应参与哈希的精确字符串。

## Gate

`filter-catalog validate` 与 `qwq-data verify all` 同时校验：

- metadata 中 15 项 adjustment 与 Python 强类型字段完全一致；
- 分类、预设、分类内排序和推荐引用唯一且有效；
- `defaultStrength`、15 项 adjustment 范围和 `original` identity；
- canonical digest、固定 digest vector 与 release 不可变路径；
- App bootstrap 为 canonical 的精确生成投影；
- alpha/beta/gamma/prod manifest 全覆盖并引用同一 artifact；
- 四环境 input 的 `deliveryMode=immutable_release`，不得退回 seed 语义。
