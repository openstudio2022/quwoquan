#!/usr/bin/env python3
"""Go 侧 nil 语义门禁：nil 只表达「缺席」，不表达「失败」也不表达「空集合」。

规格：`specs/feature-tree/runtime/system-architecture-and-engineering-guide/
absent-empty-failure-nullability/spec.md`（REQ-003 / REQ-004）。

两条判据，形态不同因为存量不同：

**硬 BLOCK：出站 wire 上的值类型 `bool` + `omitempty`，以及会因空而消失的列表。**

`omitempty` 对值类型 bool 意味着 `false` 被整个省略。端侧拿到的「键不存在」既可能
是服务端没这个字段，也可能是它确实为 false，两种含义压成一个。而端侧 codegen 对
必填 bool 生成的是 fail-closed 校验，键一旦消失就是解码失败——`false` 会变成一次
线上解码错误。`*bool` + `omitempty` 不在此列：nil 省略、`&false` 输出 `false`，
指针在这里恰好把三态表达对了。列表同理：`omitempty` 让空列表整个消失，而 REQ-003
要求它稳定序列化为 `[]`。

**「出站」按数据流判定，不按目录名。** 早先的口径是「文件路径含
`adapters/inbound/http`」，于是 `CommentCommandResult.Replayed` 这个真实缺陷从眼前
溜过去了：DTO 定义在 `application/contracts.go`，handler 只是把它传给 `writeJSON`，
按目录名判定时它根本不算 wire。现在从 `writeJSON` / `httpcodec.WriteJSON` /
`json.NewEncoder(w).Encode` 的实参出发，回溯变量赋值与函数返回类型定位到 struct
定义处，再沿字段类型递归展开嵌套与列表元素。目录名不再参与判定。

`map[string]any{...}` 字面量不在其列：键是逐个写死的，不会因取值而消失。

无法静态定位类型的调用点单独报告，不计入违规——门禁只对它能证明的部分下断言，
剩下的必须可见，而不是被默默当成合规。运行时才能确定的部分（nil slice 会序列化成
`null`）由 GWT-003 的响应体断言承担，静态分析不越界猜测。

**棘轮：领域端口的 `return nil, nil`。**

`(*T, error)` 返回 `(nil, nil)` 让空返回值兼作「未命中」信号，调用方只能靠判空
猜测，而漏判的代价是 panic。未命中应当由 sentinel error 或 `AppError` 表达。
`infrastructure` 单列不计入：store 未命中有其合理性，收敛它需要先统一显式约定。

只计二元 `(nil, nil)`。`return nil, nil, err` 的第三个返回值已经在表达失败，它不属于
本条判据——按文件计数的旧口径把它一并计入，虚增了配额，也让「降到零」这个目标失去
意义。

计数按**所在函数**而不是按文件：配额挂在文件上时，同一文件内删一处、在另一个函数
里添一处，总数不变，门禁看不见。函数名比行号稳定，不会因无关编辑漂移。

**棘轮：契约字段的可空性未显式声明。**

字段没写 `NOT_NULL` / `NULLABLE` / `PK` 时，各 codegen 管线只能按自己的缺省规则
推定——assistant wire 推定为可空，其它管线未必。同一个字段因此可以在不同管线得到
不同的可空性，而契约上看不出任何差别。`NOT_BLANK` / `DEFAULT_*` / `FK_*` 虽然通常
隐含非空，但那是读者的推断而不是声明，不足以消除推定。

补声明会把这些字段从「推定可空」变成 fail-closed 必填，属于行为变更，需要
`api_integration` 先行验证，因此以棘轮承载而不是就地清零。
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True

_BOOTSTRAP = next(
    p for p in Path(__file__).resolve().parents if (p / "repository_root.py").is_file()
)
sys.path.insert(0, str(_BOOTSTRAP))
from repository_root import repository_root  # noqa: E402

SERVICE_ROOT = repository_root() / "quwoquan_service"
BASELINE_PATH = Path(__file__).with_name("nil_semantics_baseline.json")

DISPOSABLE_DIRS = {".qwq_output", ".git", "vendor"}

#: Go module 名。import path 去掉它就是相对 `SERVICE_ROOT` 的包目录。
MODULE_PREFIX = "quwoquan_service/"

#: 领域端口层。`infrastructure` 刻意不在内，见模块 docstring。
PORT_LAYERS = ("application", "domain", "adapters")

#: 出站序列化入口。第三个实参（`Encode` 是第一个）是真正被写到 wire 上的值。
WRITE_JSON_CALL = re.compile(
    r"\b(?:writeJSON|WriteJSON)\s*\(\s*\w+\s*,\s*[^,]+?,\s*(.+?)\s*"
    r'(?:,\s*"[^"]*"\s*)?\)\s*(?://.*)?$'
)
ENCODE_CALL = re.compile(r"json\.NewEncoder\(\s*\w+\s*\)\.Encode\(\s*(.+?)\s*\)")

STRUCT_DECL = re.compile(r"^type\s+(\w+)\s+struct\s*\{")
IMPORT_SPEC = re.compile(r'^\s*(?:(\w+|\.)\s+)?"([^"]+)"\s*$')
TAGGED_FIELD = re.compile(r"^\s*(\w+)\s+(\S.*?)\s+`([^`]*)`\s*(?://.*)?$")
JSON_TAG = re.compile(r'json:"([^"]*)"')

#: 复合字面量与取址：`Type{`、`pkg.Type{`、`&Type{`。
COMPOSITE_LITERAL = re.compile(r"^&?([\w.]+)\s*\{")
#: 调用：`f(...)`、`recv.Method(...)`、`pkg.Func(...)`。
CALL_EXPRESSION = re.compile(r"^([\w.]+)\s*\(")

#: 二元 `(nil, nil)`。`(?!,)` 排掉 `return nil, nil, err` —— 第三个返回值已经在
#: 表达失败，那不是「空返回值兼作未命中信号」。
RETURN_NIL_NIL = re.compile(r"\breturn\s+nil,\s*nil\s*(?!,)")

#: `func Name(` 与 `func (r *Recv) Name(` 两种声明形式。
FUNC_DECL = re.compile(r"^func\s+(?:\([^)]*\)\s*)?(\w+)")

#: 能独自确定字段可空性的约束。`PK` 计入：主键非空是关系模型的定义，不是推断。
NULLABILITY_CONSTRAINTS = frozenset({"NOT_NULL", "NULLABLE", "PK"})


def _go_sources() -> list[Path]:
    return [
        path
        for path in SERVICE_ROOT.rglob("*.go")
        if not DISPOSABLE_DIRS.intersection(path.relative_to(SERVICE_ROOT).parts)
        and not path.name.endswith("_test.go")
    ]


def _relative(path: Path) -> str:
    return path.relative_to(SERVICE_ROOT).as_posix()


#: 语言内建与标准库标量。它们没有 struct 定义，递归到这里就停。
SCALAR_TYPES = frozenset(
    {
        "any", "bool", "byte", "complex64", "complex128", "error", "float32",
        "float64", "int", "int8", "int16", "int32", "int64", "rune", "string",
        "uint", "uint8", "uint16", "uint32", "uint64", "uintptr",
    }
)


class GoFile:
    """一个 Go 源文件的解析视图。`directory` 就是它的包。"""

    def __init__(self, path: Path) -> None:
        self.relative = _relative(path)
        self.directory = str(Path(self.relative).parent)
        self.lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        self.imports = _parse_imports(self.lines)


def _parse_imports(lines: list[str]) -> dict[str, str]:
    """`别名 -> 包目录`，只收本 module 内的包。"""
    aliases: dict[str, str] = {}
    inside = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("import ("):
            inside = True
            continue
        if inside and stripped == ")":
            break
        if not inside and not stripped.startswith("import "):
            continue
        spec = IMPORT_SPEC.match(stripped.removeprefix("import "))
        if not spec:
            continue
        alias, target = spec.group(1), spec.group(2)
        if not target.startswith(MODULE_PREFIX):
            continue
        aliases[alias or target.rsplit("/", 1)[-1]] = target[len(MODULE_PREFIX) :]
    return aliases


def _element_type(expression: str) -> tuple[str, bool]:
    """剥掉 `*` / `[]` / `map[...]`，返回 `(基础类型, 是否 JSON 数组)`。

    `[]byte` 不算数组：它序列化成 base64 字符串。
    """
    expression = expression.strip()
    is_array = False
    while True:
        if expression.startswith("[]"):
            expression, is_array = expression[2:].strip(), True
            continue
        if expression.startswith("*"):
            expression = expression[1:].strip()
            continue
        nested = re.match(r"^map\[[^\]]*\]\s*(.+)$", expression)
        if nested:
            expression = nested.group(1).strip()
            continue
        break
    if expression in ("byte", "uint8"):
        is_array = False
    return expression, is_array


def _qualify(name: str, source: GoFile) -> tuple[str, str] | None:
    """把类型表达式解析成 `(包目录, 类型名)`。标量与外部包返回 `None`。

    不要求首字母大写：`mediaAssetHTTPResponse` 这类包内私有 struct 一样会被
    序列化出去，按导出性过滤会把它们整批漏掉。是不是 struct 由 struct 索引说话。
    """
    if "." in name:
        alias, _, bare = name.partition(".")
        directory = source.imports.get(alias)
        return (directory, bare) if directory else None
    if not name or name in SCALAR_TYPES:
        return None
    return (source.directory, name)


class StructDef:
    def __init__(self, relative: str, directory: str) -> None:
        self.relative = relative
        self.directory = directory
        #: `(字段名, 类型表达式, json 名, omitempty, 行号)`
        self.fields: list[tuple[str, str, str, bool, int]] = []


def _index_structs(sources: list[GoFile]) -> dict[tuple[str, str], StructDef]:
    structs: dict[tuple[str, str], StructDef] = {}
    for source in sources:
        index = 0
        while index < len(source.lines):
            declaration = STRUCT_DECL.match(source.lines[index])
            if not declaration:
                index += 1
                continue
            definition = StructDef(source.relative, source.directory)
            depth = 1
            index += 1
            while index < len(source.lines) and depth > 0:
                line = source.lines[index]
                if depth == 1:
                    _collect_field(definition, line, index + 1)
                depth += line.count("{") - line.count("}")
                index += 1
            structs[(source.directory, declaration.group(1))] = definition
    return structs


def _collect_field(definition: StructDef, line: str, line_number: int) -> None:
    stripped = line.strip()
    if not stripped or stripped.startswith("//") or stripped in ("}", "{"):
        return
    tagged = TAGGED_FIELD.match(line)
    if tagged:
        name, type_expression, tag = tagged.group(1), tagged.group(2), tagged.group(3)
        json_tag = JSON_TAG.search(tag)
        parts = json_tag.group(1).split(",") if json_tag else []
        json_name = parts[0] if parts and parts[0] else name
        if json_name == "-":
            return
        definition.fields.append(
            (name, type_expression, json_name, "omitempty" in parts[1:], line_number)
        )
        return
    untagged = re.match(r"^\s*(\w+)\s+(\S.*?)\s*(?://.*)?$", line)
    if untagged and not untagged.group(2).startswith("("):
        definition.fields.append(
            (untagged.group(1), untagged.group(2), untagged.group(1), False, line_number)
        )


def _matching_paren(text: str, start: int) -> int:
    depth = 0
    for index in range(start, len(text)):
        if text[index] == "(":
            depth += 1
        elif text[index] == ")":
            depth -= 1
            if depth == 0:
                return index
    return -1


def _joined_declaration(lines: list[str], index: int) -> str:
    """把可能跨行的 `func` 声明拼成一行，直到行尾出现 `{`。

    真实签名经常换行（参数一行一个），只看首行会漏掉返回类型——`replayed` 那处
    缺陷之所以能逃过第一版扫描，就是因为 `CommentService.CreateComment` 的签名
    跨了多行。
    """
    buffer = lines[index]
    cursor = index
    while cursor + 1 < len(lines) and not buffer.rstrip().endswith("{"):
        if cursor - index > 40:
            break
        cursor += 1
        buffer = f"{buffer} {lines[cursor].strip()}"
    return buffer


def _split_signature(declaration: str) -> tuple[str, str] | None:
    """`func (r *R) Name(args) (A, error) {` -> `("Name", "(A, error)")`。"""
    rest = declaration.removeprefix("func").strip()
    if rest.startswith("("):
        end = _matching_paren(rest, 0)
        if end < 0:
            return None
        rest = rest[end + 1 :].strip()
    name = re.match(r"^(\w+)", rest)
    if not name:
        return None
    rest = rest[len(name.group(1)) :].strip()
    if rest.startswith("["):
        depth = 0
        for index, character in enumerate(rest):
            depth += (character == "[") - (character == "]")
            if depth == 0:
                rest = rest[index + 1 :].strip()
                break
    if not rest.startswith("("):
        return None
    end = _matching_paren(rest, 0)
    if end < 0:
        return None
    return name.group(1), rest[end + 1 :].strip().removesuffix("{").strip()


def _index_returns(
    sources: list[GoFile],
) -> tuple[dict[tuple[str, str], str], dict[str, set[tuple[str, str]]]]:
    """`(包内函数 -> 首个返回类型, 函数名 -> {(包, 首个返回类型)})`。

    按名字的全局索引是为了跟过接口调用：handler 手里只有 `h.service.CreateComment`，
    实现体的接收者类型无从静态得知，但方法名足以定位候选返回类型。同名多义时全部
    纳入——宁可多查几个类型，也不要漏掉真正写到 wire 上的那个。
    """
    by_package: dict[tuple[str, str], str] = {}
    by_name: dict[str, set[tuple[str, str]]] = {}
    for source in sources:
        for index, line in enumerate(source.lines):
            if not line.startswith("func "):
                continue
            signature = _split_signature(_joined_declaration(source.lines, index))
            if not signature:
                continue
            name, returns = signature
            first = returns.removeprefix("(").removesuffix(")").split(",")[0].strip()
            if not first or first == "error":
                continue
            by_package.setdefault((source.directory, name), first)
            by_name.setdefault(name, set()).add((source.directory, first))
    return by_package, by_name


def _resolve_expression(
    expression: str,
    source: GoFile,
    returns_by_package: dict[tuple[str, str], str],
    returns_by_name: dict[str, set[tuple[str, str]]],
) -> set[tuple[str, str]]:
    """表达式 -> 它可能的 struct 类型。空集表示无法静态确定。"""
    expression = expression.strip()
    if expression.startswith("map[") or expression.startswith("[]map["):
        return set()

    literal = COMPOSITE_LITERAL.match(expression)
    if literal:
        qualified = _qualify(_element_type(literal.group(1))[0], source)
        return {qualified} if qualified else set()

    call = CALL_EXPRESSION.match(expression)
    if call:
        callee = call.group(1)
        bare = callee.rsplit(".", 1)[-1]
        local = returns_by_package.get((source.directory, bare))
        if local:
            qualified = _qualify(_element_type(local)[0], source)
            return {qualified} if qualified else set()
        found: set[tuple[str, str]] = set()
        for directory, return_type in returns_by_name.get(bare, set()):
            element = _element_type(return_type)[0]
            if "." in element:
                alias, _, name = element.partition(".")
                # 返回类型写在被调方文件里，别名要按那个包解析；这里退化为
                # 「同名类型定义在被调方包内」，够用且不会跨包乱指。
                found.add((directory, name))
            elif element and element not in SCALAR_TYPES:
                found.add((directory, element))
        return found
    return set()


def _trace_variable(
    variable: str,
    body: list[tuple[int, str]],
    source: GoFile,
    returns_by_package: dict[tuple[str, str], str],
    returns_by_name: dict[str, set[tuple[str, str]]],
) -> set[tuple[str, str]]:
    """在函数体内回溯变量最近一次赋值，解析其类型。"""
    declared = re.compile(rf"^\s*var\s+{re.escape(variable)}\s+(\S.*?)\s*$")
    assigned = re.compile(
        rf"^\s*{re.escape(variable)}\s*(?:,\s*[\w_]+\s*)*(?::?=)\s*(.+?)\s*$"
    )
    for _, line in reversed(body):
        explicit = declared.match(line)
        if explicit:
            qualified = _qualify(_element_type(explicit.group(1))[0], source)
            return {qualified} if qualified else set()
        binding = assigned.match(line)
        if binding:
            return _resolve_expression(
                binding.group(1), source, returns_by_package, returns_by_name
            )
    return set()


def _outbound_roots(
    sources: list[GoFile],
    returns_by_package: dict[tuple[str, str], str],
    returns_by_name: dict[str, set[tuple[str, str]]],
) -> tuple[set[tuple[str, str]], list[str]]:
    """所有出站序列化调用点解析出的根类型，以及无法解析的调用点。"""
    roots: set[tuple[str, str]] = set()
    unresolved: list[str] = []
    for source in sources:
        for index, line in enumerate(source.lines):
            match = WRITE_JSON_CALL.search(line.strip()) or ENCODE_CALL.search(line)
            if not match:
                continue
            argument = match.group(1).strip()
            if argument.startswith("map["):
                continue
            if _is_opaque_relay(source.lines, index, argument):
                continue
            resolved = _resolve_expression(
                argument, source, returns_by_package, returns_by_name
            )
            if not resolved and re.fullmatch(r"[\w.]+", argument):
                body = _enclosing_body(source.lines, index)
                resolved = _trace_variable(
                    argument.split(".")[0], body, source,
                    returns_by_package, returns_by_name,
                )
            if resolved:
                roots |= resolved
            else:
                unresolved.append(f"{source.relative}:{index + 1}: {argument}")
    return roots, unresolved


def _is_opaque_relay(lines: list[str], target: int, argument: str) -> bool:
    """写出的值是本函数的 `any` 形参时，这里只是个转发器。

    每个服务都有一个 `func writeJSON(w, status, payload any)`，真正的类型在它的
    调用方。把这些转发器计成「无法定位」会淹没真正需要人看的调用点。
    """
    if not re.fullmatch(r"\w+", argument):
        return False
    for index in range(target, -1, -1):
        if not lines[index].startswith("func "):
            continue
        declaration = _joined_declaration(lines, index)
        return bool(
            re.search(rf"\b{re.escape(argument)}\s+(?:any|interface\{{\}})\b", declaration)
        )
    return False


def _enclosing_body(lines: list[str], target: int) -> list[tuple[int, str]]:
    """目标行所在函数体内、目标行之前的那些行。"""
    start = 0
    for index in range(target, -1, -1):
        if lines[index].startswith("func "):
            start = index
            break
    return [(index, lines[index]) for index in range(start, target)]


def _reachable_structs(
    roots: set[tuple[str, str]],
    structs: dict[tuple[str, str], StructDef],
    sources_by_directory: dict[str, GoFile],
) -> set[tuple[str, str]]:
    """从根类型沿字段类型展开，含嵌套 struct 与列表元素。"""
    seen: set[tuple[str, str]] = set()
    pending = [root for root in roots if root in structs]
    while pending:
        current = pending.pop()
        if current in seen:
            continue
        seen.add(current)
        definition = structs[current]
        owner = sources_by_directory.get(definition.directory)
        if owner is None:
            continue
        for _, type_expression, _, _, _ in definition.fields:
            element = _element_type(type_expression)[0]
            qualified = _qualify(element, owner)
            if qualified and qualified in structs and qualified not in seen:
                pending.append(qualified)
    return seen


#: 出站列表棘轮的身份前缀，和 `return nil, nil` 的函数名身份区分开。
LIST_IDENTITY_PREFIX = "wire-list:"


def _wire_findings(
    sources: list[GoFile],
) -> tuple[list[str], Ratchet, list[str]]:
    """`(bool 违规, 出站列表棘轮, 无法静态定位的调用点)`。

    bool 硬 BLOCK：`false` 消失会直接打成端侧解码失败，且修复只是删掉 `omitempty`。
    列表走棘轮：删掉 `omitempty` 之后 nil 切片会序列化成 `null`，同样违反 REQ-003，
    所以每一处都要连着构造期归一化一起改，逐个 DTO 裁决，不能一把梭。
    """
    structs = _index_structs(sources)
    returns_by_package, returns_by_name = _index_returns(sources)
    roots, unresolved = _outbound_roots(sources, returns_by_package, returns_by_name)
    sources_by_directory: dict[str, GoFile] = {}
    for source in sources:
        sources_by_directory.setdefault(source.directory, source)

    bool_violations: list[str] = []
    lists: Ratchet = {}
    for key in sorted(_reachable_structs(roots, structs, sources_by_directory)):
        definition = structs[key]
        for name, type_expression, json_name, omitempty, line_number in definition.fields:
            if not omitempty:
                continue
            if type_expression.strip() == "bool":
                bool_violations.append(
                    f"{definition.relative}:{line_number}: {key[1]}.{name} "
                    f'（json:"{json_name}"）是值类型 bool + omitempty，false 会整个消失'
                )
            elif _element_type(type_expression)[1]:
                identity = f"{LIST_IDENTITY_PREFIX}{key[1]}.{name}"
                bucket = lists.setdefault(definition.relative, {})
                bucket[identity] = bucket.get(identity, 0) + 1
    return bool_violations, lists, unresolved


def _port_layer(relative: str) -> str | None:
    parts = relative.split("/")
    for layer in PORT_LAYERS:
        if layer in parts:
            return layer
    return None


#: 棘轮形状：`文件路径 -> {身份 -> 计数}`。Go 的身份是函数名，契约的身份是字段名。
Ratchet = dict[str, dict[str, int]]


def scan() -> tuple[list[str], list[str], Ratchet]:
    """`(出站 wire 违规, 无法静态定位的出站调用点, 棘轮身份计数)`。

    两类棘轮合在一张表里，外层 key 是文件路径，因此彼此不会串号。
    """
    sources = [GoFile(path) for path in _go_sources()]
    wire_violations, list_ratchet, unresolved = _wire_findings(sources)

    ratchet: Ratchet = {}
    for relative, identities in list_ratchet.items():
        ratchet.setdefault(relative, {}).update(identities)
    for source in sources:
        if "infrastructure" in source.relative.split("/") or not _port_layer(
            source.relative
        ):
            continue
        identities = _nil_nil_identities("\n".join(source.lines))
        if identities:
            ratchet.setdefault(source.relative, {}).update(identities)

    ratchet.update(_implicit_nullability_identities())
    return wire_violations, unresolved, ratchet


def _nil_nil_identities(text: str) -> dict[str, int]:
    """每个函数内的二元 `return nil, nil` 计数。

    闭包内的 return 归属外层函数：函数级已经足以让「换个地方再加一处」露出来，
    再细就会被无关编辑推着变。
    """
    counts: dict[str, int] = {}
    current = "<file-scope>"
    for line in text.splitlines():
        declaration = FUNC_DECL.match(line)
        if declaration:
            current = declaration.group(1)
        if RETURN_NIL_NIL.search(line):
            counts[current] = counts.get(current, 0) + 1
    return counts


def _implicit_nullability_identities() -> Ratchet:
    """每个 fields.yaml 中可空性无法从约束确定的字段名。"""
    import yaml

    found: Ratchet = {}
    for path in sorted((SERVICE_ROOT / "services").rglob("contracts/**/fields.yaml")):
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(document, dict):
            continue
        fields = document.get("fields")
        if not isinstance(fields, list):
            continue
        implicit: dict[str, int] = {}
        for field in fields:
            if not isinstance(field, dict):
                continue
            constraints = field.get("constraints")
            if not isinstance(constraints, list):
                constraints = []
            if not NULLABILITY_CONSTRAINTS.intersection(constraints):
                name = field.get("name")
                if isinstance(name, str) and name:
                    implicit[name] = implicit.get(name, 0) + 1
        if implicit:
            found[_relative(path)] = implicit
    return found


def _parse_baseline(document: object) -> Ratchet:
    """只认 `path -> {identity -> count}`。

    旧口径的 `path -> count` 不再被接受：它无法表达身份，静默兼容会让迁移看起来
    像没发生过。结构不匹配时返回空表，由调用方按「不可比」处理。
    """
    if not isinstance(document, dict):
        return {}
    parsed: Ratchet = {}
    for key, value in document.items():
        if key == "_governance" or not isinstance(value, dict):
            continue
        parsed[key] = {
            identity: count
            for identity, count in value.items()
            if isinstance(count, int)
        }
    return parsed


def _load_baseline() -> Ratchet:
    if not BASELINE_PATH.is_file():
        return {}
    return _parse_baseline(json.loads(BASELINE_PATH.read_text(encoding="utf-8")))


def _head_baseline() -> Ratchet | None:
    """HEAD 版本的基线。`None` 表示无法比较（文件新增或旧口径）。"""
    relative = BASELINE_PATH.relative_to(repository_root()).as_posix()
    result = subprocess.run(
        ["git", "show", f"HEAD:{relative}"],
        cwd=repository_root(),
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    try:
        document = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None
    parsed = _parse_baseline(document)
    return parsed or None


def _growth_against(reference: Ratchet, candidate: Ratchet) -> list[str]:
    """`candidate` 相对 `reference` 新增的身份或变大的计数。"""
    growth: list[str] = []
    for relative in sorted(candidate):
        allowed = reference.get(relative, {})
        for identity, count in sorted(candidate[relative].items()):
            if count > allowed.get(identity, 0):
                growth.append(
                    f"{relative}:{identity} {count} 处，超出 {allowed.get(identity, 0)}"
                )
    return growth


def _write_baseline(ratchet: Ratchet) -> int:
    """写入基线。相对 HEAD 增长时拒绝写入并返回非零。

    `--update-baseline` 是唯一能改动配额的入口，所以单调性必须在这里也成立：
    否则「跑一下 update」就是无痕销账。
    """
    head = _head_baseline()
    if head is not None:
        growth = _growth_against(head, ratchet)
        if growth:
            print("[nil-semantics] FAIL: --update-baseline 只能收紧，不能放大")
            for item in growth:
                print(f"    {item}")
            print("    先把新增的空返回值改成 sentinel error 或 AppError。")
            return 1

    existing: dict[str, object] = {}
    if BASELINE_PATH.is_file():
        existing = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    document: dict[str, object] = {}
    if "_governance" in existing:
        document["_governance"] = existing["_governance"]
    for relative in sorted(ratchet):
        document[relative] = dict(sorted(ratchet[relative].items()))
    BASELINE_PATH.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    total = sum(sum(v.values()) for v in ratchet.values())
    print(f"OK: nil 语义基线已更新（{total} 处 / {len(ratchet)} 文件）")
    return 0


def _total(ratchet: Ratchet) -> int:
    return sum(sum(identities.values()) for identities in ratchet.values())


def _ratchet_kind(relative: str, identity: str) -> str:
    if relative.endswith("fields.yaml"):
        return "字段可空性未声明"
    if identity.startswith(LIST_IDENTITY_PREFIX):
        return "出站列表 + omitempty"
    return "return nil, nil"


def main() -> int:
    wire_violations, unresolved, ratchet = scan()

    if "--update-baseline" in sys.argv:
        return _write_baseline(ratchet)

    failures: list[str] = []

    if wire_violations:
        failures.append(
            f"出站 wire 上有 {len(wire_violations)} 处字段会因取值而整个消失："
        )
        failures.extend(f"    {item}" for item in wire_violations)
        failures.append(
            "    去掉 omitempty；确需区分「未设置」与「false」时改用 *bool，"
            "列表则在构造期归一化成空切片。"
        )

    baseline = _load_baseline()
    regressions = []
    for relative in sorted(ratchet):
        allowed = baseline.get(relative, {})
        for identity, count in sorted(ratchet[relative].items()):
            quota = allowed.get(identity, 0)
            if count > quota:
                regressions.append(
                    f"{relative} 的 {identity}: {_ratchet_kind(relative, identity)} "
                    f"{count} 处，超出基线 {quota}"
                )
    if regressions:
        failures.append(f"棘轮回退 {len(regressions)} 处（只减不增）：")
        failures.extend(f"    {item}" for item in regressions)
        failures.append(
            "    未命中用 sentinel error 或 AppError 表达，让调用方无从漏判；"
            "新契约字段必须显式写 NOT_NULL 或 NULLABLE，不要留给生成器推定；"
            "出站列表去掉 omitempty 的同时要在构造期归一化成空切片，"
            "否则 nil 会序列化成 null，换一种方式违反同一条 REQ-003。"
        )

    #: 基线里已经没有对应实现的条目。留着它就是一份可以随时取用的配额：
    #: 今天删掉一处，明天在同一个函数里加回来，门禁全程绿。
    stale = []
    for relative in sorted(baseline):
        present = ratchet.get(relative, {})
        for identity, quota in sorted(baseline[relative].items()):
            actual = present.get(identity, 0)
            if actual < quota:
                stale.append(f"{relative} 的 {identity}: 实测 {actual} 处，基线仍写 {quota}")
    if stale:
        failures.append(f"基线有 {len(stale)} 处未随实现收紧（配额不得预留）：")
        failures.extend(f"    {item}" for item in stale)
        failures.append(
            "    债务下降后必须同批固化：python3 "
            "quwoquan_service/scripts/verify/structure/verify_nil_semantics.py --update-baseline"
        )

    if failures:
        print("[nil-semantics] FAIL")
        for line in failures:
            print(f"  - {line}" if not line.startswith("    ") else line)
        return 1

    unresolved_note = (
        f"；{len(unresolved)} 个出站调用点的类型无法静态定位，由 GWT-003 的响应体断言兜底"
        if unresolved
        else ""
    )
    print(
        f"[nil-semantics] OK: 出站 wire 无 false/空列表消失；"
        f"棘轮项 {_total(ratchet)} 处与基线逐身份持平{unresolved_note}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
