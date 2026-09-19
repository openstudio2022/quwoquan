package main

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// 退役取值的 canonical 声明只住在 _shared/types.yaml 的 retired_enum_values，本
// 生成器是它唯一的 Go 投影。这里用真实契约视图跑投影并写进 t.TempDir()，既不碰
// 仓内 generated 产物，也不用 fixture 顶替真相源。
func TestRetiredContentTypeProjectionMirrorsCanonicalDeclaration(t *testing.T) {
	t.Parallel()

	source := contentTestContractSource(t)
	groups, err := loadServiceRoutes(source, "content-service")
	if err != nil {
		t.Fatalf("loadServiceRoutes() error = %v", err)
	}
	output := t.TempDir()
	if err := generateContracts(source, groups, output); err != nil {
		t.Fatalf("generateContracts() error = %v", err)
	}
	raw, err := os.ReadFile(filepath.Join(output, "content", "post", "contracts.go"))
	if err != nil {
		t.Fatalf("read projected post contracts: %v", err)
	}
	rendered := string(raw)

	var shared struct {
		Enums             map[string][]string    `yaml:"enums"`
		RetiredEnumValues []retiredEnumValueYAML `yaml:"retired_enum_values"`
	}
	if err := source.Decode("_shared/types.yaml", &shared); err != nil {
		t.Fatalf("decode canonical shared types: %v", err)
	}
	declared := retiredValuesForEnum(shared.RetiredEnumValues, "ContentType")
	if len(declared) == 0 {
		t.Fatal("canonical retired_enum_values declares no ContentType member; this test must not pass on an empty projection")
	}

	for _, record := range declared {
		want := fmt.Sprintf(
			"{Enum: %q, RetiredValue: %q},",
			record.Enum,
			record.RetiredValue,
		)
		if !strings.Contains(rendered, want) {
			t.Errorf("projected contracts.go is missing canonical record %s", want)
		}
		// 退役取值与合法闭集互斥：投影同时出现在 Allowed 集合里就是把它放回了
		// 读写通道，而不是留作一次性迁移输入。
		for _, live := range shared.Enums["ContentType"] {
			if live == record.RetiredValue {
				t.Errorf(
					"retired ContentType %q is still declared in the live closed set",
					record.RetiredValue,
				)
			}
		}
		allowed := rendered[strings.Index(rendered, "var AllowedContentTypes"):]
		allowed = allowed[:strings.Index(allowed, "\n}")]
		if strings.Contains(allowed, fmt.Sprintf("%q", record.RetiredValue)) {
			t.Errorf(
				"AllowedContentTypes still lists retired value %q",
				record.RetiredValue,
			)
		}
	}
	if got := strings.Count(rendered, "RetiredValue: "); got != len(declared) {
		t.Errorf("projected retired record count = %d, want %d", got, len(declared))
	}
	if !strings.Contains(rendered, "func IsRetiredContentType(value string) bool {") {
		t.Error("projection must expose IsRetiredContentType so consumers stop spelling retired literals")
	}
}

// 记录的两半必须同时成立：projection 不得渲染出没有 enum 归属的裸退役取值，也
// 不得把别的 enum 的退役取值算进 ContentType。
func TestRetiredValuesForEnumDropsUnboundRecords(t *testing.T) {
	t.Parallel()

	records := []retiredEnumValueYAML{
		{Enum: "ContentType", RetiredValue: "second"},
		{Enum: "ContentType", RetiredValue: "first"},
		{Enum: "ContentType", RetiredValue: "   "},
		{Enum: "MediaType", RetiredValue: "other"},
		{Enum: "", RetiredValue: "orphan"},
	}
	got := retiredValuesForEnum(records, "ContentType")
	want := []retiredEnumValueData{
		{Enum: "ContentType", RetiredValue: "first"},
		{Enum: "ContentType", RetiredValue: "second"},
	}
	if len(got) != len(want) {
		t.Fatalf("retiredValuesForEnum() = %#v, want %#v", got, want)
	}
	for index := range want {
		if got[index] != want[index] {
			t.Errorf("record %d = %#v, want %#v", index, got[index], want[index])
		}
	}
}
