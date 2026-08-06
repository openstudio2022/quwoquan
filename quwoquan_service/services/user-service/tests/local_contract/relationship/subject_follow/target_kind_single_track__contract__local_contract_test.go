package local_contract

import (
	"errors"
	"os"
	"path/filepath"
	"runtime"
	"testing"

	sfmodel "quwoquan_service/services/user-service/internal/relationship/subject_follow/domain/model"

	"gopkg.in/yaml.v3"
)

// TestSubjectFollowTargetKindMatchesAggregateWriteDomain 固定写侧值域单轨：
// SubjectFollow 的 subjectType 只能引用对象自有 SubjectFollowTargetKind，
// 且该枚举的取值必须与聚合 NewCommand 的准入行为逐值一致。
func TestSubjectFollowTargetKindMatchesAggregateWriteDomain(t *testing.T) {
	t.Parallel()

	contract := readSubjectFollowFieldsContract(t)
	targetKind, declared := contract.Enums["SubjectFollowTargetKind"]
	if !declared {
		t.Fatal("subject_follow/fields.yaml must own SubjectFollowTargetKind")
	}
	if len(targetKind.Values) == 0 {
		t.Fatal("SubjectFollowTargetKind must declare a non-empty closed value set")
	}
	for _, value := range targetKind.Values {
		if value == "persona" {
			t.Fatal("persona belongs to PersonaRelationship and must stay out of the write domain")
		}
		if _, err := sfmodel.NewCommand(
			sfmodel.CommandFollow, "ps_1", value, "subject_1", "", "key",
		); err != nil {
			t.Fatalf("SubjectFollowTargetKind value %q is rejected by the aggregate: %v", value, err)
		}
	}
	if _, err := sfmodel.NewCommand(
		sfmodel.CommandFollow, "ps_1", "persona", "subject_1", "", "key",
	); !errors.Is(err, sfmodel.ErrInvalidSubjectType) {
		t.Fatalf("aggregate must reject persona with ErrInvalidSubjectType, got %v", err)
	}
}

// TestSubjectFollowWriteContractDoesNotReuseReadUnion 固定读写值域拆分：
// _shared FollowSubjectKind 是关注频道读模型的并集值域（含 persona），
// 写侧契约不得复用它，否则读并集会被当成写许可。
func TestSubjectFollowWriteContractDoesNotReuseReadUnion(t *testing.T) {
	t.Parallel()

	contract := readSubjectFollowFieldsContract(t)
	for _, field := range contract.Fields {
		if field.EnumRef == "FollowSubjectKind" {
			t.Fatalf("aggregate field %s must not reuse the read union FollowSubjectKind", field.Name)
		}
	}
	for typeName, wireType := range contract.Types {
		for _, field := range wireType.Fields {
			if field.EnumRef == "FollowSubjectKind" {
				t.Fatalf("%s.%s must not reuse the read union FollowSubjectKind", typeName, field.Name)
			}
		}
	}

	readUnion := readSharedEnumValues(t, "FollowSubjectKind")
	if !containsValue(readUnion, "persona") {
		t.Fatal("FollowSubjectKind must keep persona; it is the read union of the following channel")
	}
	for _, value := range contract.Enums["SubjectFollowTargetKind"].Values {
		if !containsValue(readUnion, value) {
			t.Fatalf("write value %q is not projected by the read union FollowSubjectKind", value)
		}
	}
}

type subjectFollowFieldsContract struct {
	Fields []subjectFollowContractField `yaml:"fields"`
	Types  map[string]struct {
		Fields []subjectFollowContractField `yaml:"fields"`
	} `yaml:"types"`
	Enums map[string]struct {
		Values []string `yaml:"values"`
	} `yaml:"enums"`
}

type subjectFollowContractField struct {
	Name    string `yaml:"name"`
	EnumRef string `yaml:"enum_ref"`
}

func readSubjectFollowFieldsContract(t *testing.T) subjectFollowFieldsContract {
	t.Helper()
	path := filepath.Join(
		userServiceContractRoot(t),
		"contracts", "relationship", "subject_follow", "fields.yaml",
	)
	raw, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read %s: %v", path, err)
	}
	var contract subjectFollowFieldsContract
	if err := yaml.Unmarshal(raw, &contract); err != nil {
		t.Fatalf("decode %s: %v", path, err)
	}
	return contract
}

func readSharedEnumValues(t *testing.T, name string) []string {
	t.Helper()
	path := filepath.Join(
		userServiceContractRoot(t), "..", "..",
		"contracts", "metadata", "_shared", "types.yaml",
	)
	raw, err := os.ReadFile(filepath.Clean(path))
	if err != nil {
		t.Fatalf("read %s: %v", path, err)
	}
	var shared struct {
		Enums map[string][]string `yaml:"enums"`
	}
	if err := yaml.Unmarshal(raw, &shared); err != nil {
		t.Fatalf("decode shared types: %v", err)
	}
	values, declared := shared.Enums[name]
	if !declared {
		t.Fatalf("_shared/types.yaml must declare %s", name)
	}
	return values
}

func userServiceContractRoot(t *testing.T) string {
	t.Helper()
	_, file, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("resolve test file path")
	}
	return filepath.Clean(filepath.Join(filepath.Dir(file), "..", "..", "..", ".."))
}

func containsValue(values []string, target string) bool {
	for _, value := range values {
		if value == target {
			return true
		}
	}
	return false
}
