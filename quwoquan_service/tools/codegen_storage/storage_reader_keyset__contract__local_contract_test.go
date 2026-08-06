package main

import (
	"encoding/json"
	"os"
	"path/filepath"
	"reflect"
	"sort"
	"strings"
	"testing"

	"gopkg.in/yaml.v3"
)

// storage.yaml 的顶层键集曾经有三套互不相同、且互相看不见的答案：
// schema 允许一套、codegen_storage 读一套、readiness loader 扫一套。
// 根因是 storage.schema.json 开着 additionalProperties，权威 schema 不拒绝任何键，
// 于是「写了但 schema 不认」「读了但没人写」「schema 认但没人读」三类分歧静默共存。
//
// 本文件把 schema 确立为键集唯一真相源：
//   - additionalProperties 必须保持关闭，否则第一类分歧立刻可以重新静默产生；
//   - codegen_storage 的 reader struct 键集必须是 schema 键集的子集；
//   - schema 每个键必须被显式归入「codegen 消费」或「codegen 不消费」，
//     新增 schema 键在归类前一律 fail，杜绝第三类分歧无声扩大；
//   - reader 读的每个键必须真的有 storage.yaml 在写，杜绝第二类死读取字段。

// codegenConsumedKeys 是 codegen_storage 消费的 schema 顶层键。
// 它必须与 StorageYAML 的 yaml tag 集合逐字相等。
var codegenConsumedKeys = []string{
	"backend",
	"collections",
	"redis_cache",
	"tables",
}

// codegenIgnoredKeys 是 schema 承认、但 codegen_storage 有意不消费的顶层键。
// 每个键都要能说清由谁消费，避免「没人读」被当成「不用管」。
var codegenIgnoredKeys = map[string]string{
	"codegen":              "generation_plan.go 单独解析 codegen hints，不经 StorageYAML",
	"description":          "散文，无消费者",
	"environment_backends": "quwoquan_ops/gate/verify_runtime_log_governance.py 等可观测门禁消费",
	"fallback":             "quwoquan_app/scripts/runtime/verify_ops_event_schema_completeness.py 消费",
	"logstores":            "App/Ops 日志治理门禁消费",
	"role":                 "internal/metadata/load 派生对象存储角色",
	"streams":              "internal/metadata/load 的 publication_role 证据派生",
	"transaction":          "content-service 合约测试消费事务提交边界",
}

func repoRootForTest(t *testing.T) string {
	t.Helper()
	// 测试工作目录是 tools/codegen_storage，向上两级是 quwoquan_service。
	root, err := filepath.Abs(filepath.Join("..", ".."))
	if err != nil {
		t.Fatalf("resolve quwoquan_service root: %v", err)
	}
	return root
}

func loadStorageSchema(t *testing.T) map[string]any {
	t.Helper()
	path := filepath.Join(
		repoRootForTest(t),
		"contracts/metadata/_schemas/storage.schema.json",
	)
	raw, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read storage schema: %v", err)
	}
	var schema map[string]any
	if err := json.Unmarshal(raw, &schema); err != nil {
		t.Fatalf("decode storage schema: %v", err)
	}
	return schema
}

func schemaTopLevelKeys(t *testing.T, schema map[string]any) map[string]bool {
	t.Helper()
	properties, ok := schema["properties"].(map[string]any)
	if !ok {
		t.Fatal("storage schema has no top-level properties object")
	}
	keys := make(map[string]bool, len(properties))
	for key := range properties {
		keys[key] = true
	}
	return keys
}

func storageYAMLTags(t *testing.T) map[string]bool {
	t.Helper()
	typ := reflect.TypeOf(StorageYAML{})
	tags := make(map[string]bool, typ.NumField())
	for i := 0; i < typ.NumField(); i++ {
		tag := typ.Field(i).Tag.Get("yaml")
		name := strings.TrimSpace(strings.Split(tag, ",")[0])
		if name == "" || name == "-" {
			t.Fatalf("StorageYAML field %s has no yaml key", typ.Field(i).Name)
		}
		tags[name] = true
	}
	return tags
}

func sortedKeys(set map[string]bool) []string {
	out := make([]string, 0, len(set))
	for key := range set {
		out = append(out, key)
	}
	sort.Strings(out)
	return out
}

// TestStorageSchemaKeepsTopLevelKeySetClosed 守住键集唯一真相源的执行位本身。
// additionalProperties 一旦放开，臆造键、拼写错键与真实承重键在校验层重新同权。
func TestStorageSchemaKeepsTopLevelKeySetClosed(t *testing.T) {
	t.Parallel()

	schema := loadStorageSchema(t)
	additional, present := schema["additionalProperties"]
	if !present {
		t.Fatal("storage schema must declare additionalProperties: false at top level")
	}
	allowed, ok := additional.(bool)
	if !ok || allowed {
		t.Fatalf(
			"storage schema additionalProperties = %v, want false; "+
				"放开它会让未登记的顶层键重新静默通过校验",
			additional,
		)
	}
}

// TestCodegenStorageReaderKeySetIsSubsetOfSchema 断言 reader 键集是 schema 键集的子集。
// reader 出现 schema 不认的键，就是「读了但没人写」的死读取字段（历史上的
// version/aggregate/entity 即属此类）。
func TestCodegenStorageReaderKeySetIsSubsetOfSchema(t *testing.T) {
	t.Parallel()

	schemaKeys := schemaTopLevelKeys(t, loadStorageSchema(t))
	for _, key := range sortedKeys(storageYAMLTags(t)) {
		if !schemaKeys[key] {
			t.Errorf(
				"StorageYAML 读取顶层键 %q，但 storage.schema.json 未声明它；"+
					"要么补进 schema，要么删掉该 reader 字段",
				key,
			)
		}
	}
}

// TestStorageSchemaKeysArePartitionedByCodegenConsumption 强制 schema 每个键都被显式归类。
// 新增 schema 键若不归类即 fail，使「schema 认但没人读」无法无声扩大。
func TestStorageSchemaKeysArePartitionedByCodegenConsumption(t *testing.T) {
	t.Parallel()

	schemaKeys := schemaTopLevelKeys(t, loadStorageSchema(t))

	classified := make(map[string]bool, len(codegenConsumedKeys)+len(codegenIgnoredKeys))
	for _, key := range codegenConsumedKeys {
		if classified[key] {
			t.Fatalf("键 %q 在归类中重复", key)
		}
		classified[key] = true
	}
	for key := range codegenIgnoredKeys {
		if classified[key] {
			t.Fatalf("键 %q 同时被归为消费与不消费", key)
		}
		classified[key] = true
	}

	for _, key := range sortedKeys(schemaKeys) {
		if !classified[key] {
			t.Errorf(
				"storage.schema.json 新增顶层键 %q 未归类；"+
					"请归入 codegenConsumedKeys 或 codegenIgnoredKeys 并写明消费者",
				key,
			)
		}
	}
	for _, key := range sortedKeys(classified) {
		if !schemaKeys[key] {
			t.Errorf("归类中的键 %q 已不在 storage.schema.json 中，请同步删除", key)
		}
	}

	// reader struct 必须与「消费」分区逐字相等，杜绝分区表与实际读取漂移。
	tags := storageYAMLTags(t)
	consumed := make(map[string]bool, len(codegenConsumedKeys))
	for _, key := range codegenConsumedKeys {
		consumed[key] = true
	}
	if !reflect.DeepEqual(sortedKeys(tags), sortedKeys(consumed)) {
		t.Errorf(
			"StorageYAML yaml tag 集合 = %v，codegenConsumedKeys = %v；两者必须逐字相等",
			sortedKeys(tags), sortedKeys(consumed),
		)
	}
}

// TestCodegenStorageReaderHasNoDeadKeys 断言 reader 读的每个键真的有 storage.yaml 在写。
// 这是「读了但没人写」的正面防线：schema 关门只能保证 reader 不读 schema 外的键，
// 保证不了 reader 读一个 schema 内、却零声明的键。
func TestCodegenStorageReaderHasNoDeadKeys(t *testing.T) {
	t.Parallel()

	root := repoRootForTest(t)
	declared := map[string]int{}
	files := 0
	for _, area := range []string{"services", "control-plane"} {
		base := filepath.Join(root, area)
		err := filepath.Walk(base, func(path string, info os.FileInfo, walkErr error) error {
			if walkErr != nil {
				return walkErr
			}
			if info.IsDir() || info.Name() != "storage.yaml" {
				return nil
			}
			if !strings.Contains(filepath.ToSlash(path), "/contracts/") {
				return nil
			}
			raw, err := os.ReadFile(path)
			if err != nil {
				return err
			}
			var document map[string]any
			if err := yaml.Unmarshal(raw, &document); err != nil {
				return err
			}
			files++
			for key := range document {
				declared[key]++
			}
			return nil
		})
		if err != nil {
			t.Fatalf("walk %s: %v", area, err)
		}
	}
	if files == 0 {
		t.Fatal("no storage.yaml found; walk root is wrong")
	}

	for _, key := range sortedKeys(storageYAMLTags(t)) {
		if declared[key] == 0 {
			t.Errorf(
				"StorageYAML 读取顶层键 %q，但 %d 份 storage.yaml 中零声明；"+
					"这是死读取字段，应当删除",
				key, files,
			)
		}
	}
}
