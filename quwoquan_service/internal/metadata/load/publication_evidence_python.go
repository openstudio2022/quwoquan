package load

import (
	"bytes"
	"encoding/json"
	"fmt"
	"os/exec"
	"path/filepath"
	"sort"
)

// pythonPublicationASTScript 使用 Python 标准库 ast 解析 PyMongo 的结构事实。输入是
// stdin 上的文件路径 JSON；输出只包含由语法树证明的 collection binding、事务写入、
// 读取、进度推进、durable handoff 与 cmd 装配。注释、TODO 和错误字符串不会进入 AST
// call/assignment，因此不能形成证据。
const pythonPublicationASTScript = `
import ast
import json
import pathlib
import re
import sys

WRITE_METHODS = {
    "insert_one", "insert_many", "bulk_write", "replace_one",
    "update_one", "update_many",
}
READ_METHODS = {"find", "find_one", "aggregate"}
CLAIM_METHODS = {"find_one_and_update", "find_one_and_delete", "find_one_and_replace"}
COLLECTION_METHODS = {"get_collection"}
MAX_CALL_DEPTH = 4
RELATION_NAME = re.compile(r"^[a-z][a-z0-9_]*(?:[.$-][a-z0-9_]+)*$")


def relation_literal(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        value = node.value
        if RELATION_NAME.fullmatch(value):
            return value
    return None


def relation_binding(expression, constructor_parameters):
    if isinstance(expression, ast.Subscript):
        base = expression.value
        if isinstance(base, ast.Name) and base.id in constructor_parameters:
            return relation_literal(expression.slice)
    if isinstance(expression, ast.Call) and isinstance(expression.func, ast.Attribute):
        if expression.func.attr not in COLLECTION_METHODS or not expression.args:
            return None
        base = expression.func.value
        if isinstance(base, ast.Name) and base.id in constructor_parameters:
            return relation_literal(expression.args[0])
    return None


def function_parameters(node):
    parameters = [
        argument.arg
        for argument in list(node.args.posonlyargs) + list(node.args.args)
        if argument.arg not in {"self", "cls"}
    ]
    parameters.extend(argument.arg for argument in node.args.kwonlyargs)
    return parameters


def iter_function_nodes(function):
    stack = list(reversed(function.body))
    while stack:
        node = stack.pop()
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            continue
        yield node
        stack.extend(reversed(list(ast.iter_child_nodes(node))))


def named_reference(node):
    return node.id if isinstance(node, ast.Name) else ""


def call_name(call):
    function = call.func
    if isinstance(function, ast.Attribute):
        return function.attr
    if isinstance(function, ast.Name):
        return function.id
    return ""


def normalized_call_name(name):
    return re.sub(r"[^a-z0-9]", "", name.lower())


def is_delivery_read(name):
    normalized = normalized_call_name(name)
    return (
        normalized.startswith("claimpending")
        or normalized.startswith("leasenext")
        or (normalized.startswith("read") and "outbox" in normalized)
    )


def is_delivery_advance(name):
    normalized = normalized_call_name(name)
    return (
        (normalized.startswith("mark") and (
            "published" in normalized or "dispatched" in normalized
        ))
        or (normalized.startswith("save") and "checkpoint" in normalized)
        or normalized.startswith("acknowledge")
    )


def is_delivery_handoff(name):
    normalized = normalized_call_name(name)
    return normalized.startswith("publish") or normalized == "appenddurable"


def scan_class(path, class_node, output):
    class_methods = {
        node.name: node
        for node in class_node.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    constructor = class_methods.get("__init__")
    fields = {}
    if constructor is not None:
        constructor_parameters = set(function_parameters(constructor))
        for node in iter_function_nodes(constructor):
            targets = []
            value = None
            if isinstance(node, ast.Assign):
                targets = node.targets
                value = node.value
            elif isinstance(node, ast.AnnAssign):
                targets = [node.target]
                value = node.value
            if value is None:
                continue
            relation = relation_binding(value, constructor_parameters)
            if relation is None:
                continue
            for target in targets:
                if (
                    isinstance(target, ast.Attribute)
                    and isinstance(target.value, ast.Name)
                    and target.value.id == "self"
                ):
                    fields[target.attr] = relation
                    output["bindings"].append({"path": path, "relation": relation})

    records = []
    record_by_node = {}
    children = {}

    def register(function, parent=None):
        record = {
            "node": function,
            "parent": parent,
            "parameters": function_parameters(function),
            "transactions": set(),
            "callbackBindings": {},
            "transactionCallbacks": [],
            "calls": [],
            "accesses": [],
            "deliveryRead": False,
            "deliveryAdvance": False,
            "deliveryHandoff": False,
            "name": (
                f"{class_node.name}.{function.name}"
                if parent is None
                else f"{parent['name']}.<locals>.{function.name}"
            ),
        }
        records.append(record)
        record_by_node[id(function)] = record
        children[id(record)] = {}
        for statement in function.body:
            if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
                child = register(statement, record)
                children[id(record)][statement.name] = child
        return record

    top_records = {name: register(node) for name, node in class_methods.items()}

    def resolve_bare(record, name):
        current = record
        while current is not None:
            target = children[id(current)].get(name)
            if target is not None:
                return target
            current = current["parent"]
        return None

    def resolve_call(record, call):
        function = call.func
        if (
            isinstance(function, ast.Attribute)
            and isinstance(function.value, ast.Name)
            and function.value.id == "self"
        ):
            return top_records.get(function.attr)
        if isinstance(function, ast.Name):
            return resolve_bare(record, function.id)
        return None

    for record in records:
        for node in iter_function_nodes(record["node"]):
            if not isinstance(node, ast.Call):
                continue
            called = call_name(node)
            record["deliveryRead"] = record["deliveryRead"] or is_delivery_read(called)
            record["deliveryAdvance"] = (
                record["deliveryAdvance"] or is_delivery_advance(called)
            )
            record["deliveryHandoff"] = (
                record["deliveryHandoff"] or is_delivery_handoff(called)
            )
            if isinstance(node.func, ast.Attribute) and node.func.attr == "with_transaction":
                if node.args:
                    callback_name = named_reference(node.args[0])
                    if callback_name:
                        record["transactionCallbacks"].append(callback_name)

            target = resolve_call(record, node)
            if target is not None:
                record["calls"].append({
                    "target": target,
                    "positional": [named_reference(argument) for argument in node.args],
                    "keywords": {
                        keyword.arg: named_reference(keyword.value)
                        for keyword in node.keywords
                        if keyword.arg is not None
                    },
                })

            function = node.func
            if not isinstance(function, ast.Attribute):
                continue
            receiver = function.value
            if not (
                isinstance(receiver, ast.Attribute)
                and isinstance(receiver.value, ast.Name)
                and receiver.value.id == "self"
            ):
                continue
            relation = fields.get(receiver.attr)
            if relation is None:
                continue
            method = function.attr
            if method not in WRITE_METHODS | READ_METHODS | CLAIM_METHODS:
                continue
            session_references = {
                named_reference(keyword.value)
                for keyword in node.keywords
                if keyword.arg == "session" and named_reference(keyword.value)
            }
            record["accesses"].append({
                "relation": relation,
                "method": method,
                "sessions": session_references,
            })

    def callback_targets(record, reference):
        targets = set(record["callbackBindings"].get(reference, set()))
        direct = resolve_bare(record, reference)
        if direct is not None:
            targets.add(id(direct))
        return targets

    records_by_id = {id(record): record for record in records}
    for _ in range(MAX_CALL_DEPTH):
        changed = False
        for record in records:
            for callback_reference in record["transactionCallbacks"]:
                for target_id in callback_targets(record, callback_reference):
                    target = records_by_id[target_id]
                    if (
                        target["parameters"]
                        and target["parameters"][0] not in target["transactions"]
                    ):
                        target["transactions"].add(target["parameters"][0])
                        changed = True
            for call in record["calls"]:
                target = call["target"]
                for position, reference in enumerate(call["positional"]):
                    if not reference or position >= len(target["parameters"]):
                        continue
                    parameter = target["parameters"][position]
                    if reference in record["transactions"]:
                        if parameter not in target["transactions"]:
                            target["transactions"].add(parameter)
                            changed = True
                    callbacks = callback_targets(record, reference)
                    if callbacks:
                        target_callbacks = target["callbackBindings"].setdefault(
                            parameter, set()
                        )
                        before = len(target_callbacks)
                        target_callbacks.update(callbacks)
                        changed = changed or len(target_callbacks) != before
                for parameter, reference in call["keywords"].items():
                    if not reference or parameter not in target["parameters"]:
                        continue
                    if reference in record["transactions"]:
                        if parameter not in target["transactions"]:
                            target["transactions"].add(parameter)
                            changed = True
                    callbacks = callback_targets(record, reference)
                    if callbacks:
                        target_callbacks = target["callbackBindings"].setdefault(
                            parameter, set()
                        )
                        before = len(target_callbacks)
                        target_callbacks.update(callbacks)
                        changed = changed or len(target_callbacks) != before
        if not changed:
            break

    for record in records:
        for access in record["accesses"]:
            method = access["method"]
            relation = access["relation"]
            if method in READ_METHODS | CLAIM_METHODS:
                output["reads"].append({
                    "path": path,
                    "function": record["name"],
                    "relation": relation,
                })
            if method in WRITE_METHODS | CLAIM_METHODS:
                output["progressPaths"].append(path)
                if access["sessions"] & record["transactions"]:
                    output["writes"].append({
                        "path": path,
                        "function": record["name"],
                        "relation": relation,
                    })

    return any(
        record["deliveryRead"]
        and record["deliveryAdvance"]
        and record["deliveryHandoff"]
        for record in records
    )


paths = json.load(sys.stdin)
output = {
    "bindings": [], "writes": [], "reads": [], "progressPaths": [],
    "relayPaths": [], "composedRelayPaths": [],
}
modules = []
relay_definitions = {}
for path_value in paths:
    path = str(pathlib.Path(path_value))
    source = pathlib.Path(path).read_text(encoding="utf-8")
    module = ast.parse(source, filename=path)
    modules.append((path, module))
    for node in module.body:
        if isinstance(node, ast.ClassDef) and scan_class(path, node, output):
            output["relayPaths"].append(path)
            relay_definitions.setdefault(node.name, set()).add(path)

# Production composition is a constructor call in the service cmd tree, not merely an imported
# or defined relay. An ambiguous class name fails closed rather than blessing multiple owners.
for path, module in modules:
    if "/cmd/" not in path.replace("\\", "/"):
        continue
    imported_relays = {}
    for node in module.body:
        if not isinstance(node, ast.ImportFrom):
            continue
        for alias in node.names:
            candidates = relay_definitions.get(alias.name, set())
            if len(candidates) == 1:
                imported_relays[alias.asname or alias.name] = next(iter(candidates))
    for node in ast.walk(module):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
            continue
        relay_path = imported_relays.get(node.func.id)
        if relay_path is not None:
            output["composedRelayPaths"].append(relay_path)

for key in output:
    if key in {"progressPaths", "relayPaths", "composedRelayPaths"}:
        output[key] = sorted(set(output[key]))
    else:
        output[key] = sorted(
            {tuple(sorted(item.items())) for item in output[key]}
        )
        output[key] = [dict(item) for item in output[key]]
json.dump(output, sys.stdout, sort_keys=True, separators=(",", ":"))
`

type pythonRelationSite struct {
	Path     string `json:"path"`
	Function string `json:"function"`
	Relation string `json:"relation"`
}

type pythonPublicationASTResult struct {
	Bindings           []pythonRelationSite `json:"bindings"`
	Writes             []pythonRelationSite `json:"writes"`
	Reads              []pythonRelationSite `json:"reads"`
	ProgressPath       []string             `json:"progressPaths"`
	RelayPaths         []string             `json:"relayPaths"`
	ComposedRelayPaths []string             `json:"composedRelayPaths"`
}

func indexPythonPublicationFiles(
	index *serviceWriteIndex,
	paths []string,
) error {
	if len(paths) == 0 {
		return nil
	}
	sort.Strings(paths)
	input, err := json.Marshal(paths)
	if err != nil {
		return fmt.Errorf("encode Python publication scan input: %w", err)
	}
	command := exec.Command("python3", "-c", pythonPublicationASTScript)
	command.Stdin = bytes.NewReader(input)
	output, err := command.CombinedOutput()
	if err != nil {
		return fmt.Errorf("parse Python publication evidence: %w: %s", err, output)
	}
	var result pythonPublicationASTResult
	if err := json.Unmarshal(output, &result); err != nil {
		return fmt.Errorf("decode Python publication evidence: %w", err)
	}
	for _, binding := range result.Bindings {
		dir := filepath.Dir(binding.Path)
		index.relationBindings[binding.Relation] = appendUniqueString(
			index.relationBindings[binding.Relation], dir,
		)
	}
	for _, write := range result.Writes {
		dir := filepath.Dir(write.Path)
		index.packagesWritingTransactionally[dir] = struct{}{}
		index.transactionalWrites[write.Relation] = appendSite(
			index.transactionalWrites[write.Relation],
			writeSite{file: write.Path, function: write.Function},
		)
	}
	for _, read := range result.Reads {
		dir := filepath.Dir(read.Path)
		index.deliveryReads[read.Relation] = appendReadSite(
			index.deliveryReads[read.Relation],
			readSite{
				writeSite:  writeSite{file: read.Path, function: read.Function},
				packageDir: dir,
			},
		)
	}
	for _, path := range result.ProgressPath {
		index.packagesAdvancingProgress[filepath.Dir(path)] = struct{}{}
	}
	for _, path := range result.RelayPaths {
		if scope := publicationImplementationScope(path); scope != "" {
			index.deliveryRelayScopes[scope] = struct{}{}
		}
	}
	for _, path := range result.ComposedRelayPaths {
		if scope := publicationImplementationScope(path); scope != "" {
			index.composedDeliveryRelayScopes[scope] = struct{}{}
		}
	}
	return nil
}
