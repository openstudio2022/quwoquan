package load

import (
	"os"
	"path/filepath"
	"strings"
	"testing"

	"quwoquan_service/internal/metadata/ast"
)

func writeSharedTypes(t *testing.T, body string) string {
	t.Helper()
	dir := t.TempDir()
	shared := filepath.Join(dir, "_shared")
	if err := os.MkdirAll(shared, 0o755); err != nil {
		t.Fatalf("create shared dir: %v", err)
	}
	path := filepath.Join(shared, "types.yaml")
	if err := os.WriteFile(path, []byte(body), 0o644); err != nil {
		t.Fatalf("write shared types: %v", err)
	}
	return path
}

// 退役取值必须解析到同一文档声明的 enum 上。声明成立时它落进该 enum 的
// RetiredValues，合法闭集一个字节都不变。
func TestRetiredEnumValuesResolveOntoTheDeclaringEnum(t *testing.T) {
	t.Parallel()

	path := writeSharedTypes(t, `enums:
  ContentType: [image, video, article]
retired_enum_values:
  - {enum: ContentType, retired_value: retired_member}
`)
	enums, _, err := loadSharedDefinitions(
		filepath.Dir(filepath.Dir(path)),
		path,
		ast.EnumOwnerGlobal,
		"",
	)
	if err != nil {
		t.Fatalf("loadSharedDefinitions() error = %v", err)
	}
	if len(enums) != 1 {
		t.Fatalf("loaded %d enums, want 1", len(enums))
	}
	if got := strings.Join(enums[0].RetiredValues, ","); got != "retired_member" {
		t.Errorf("RetiredValues = %q, want %q", got, "retired_member")
	}
	if got := strings.Join(enums[0].Values, ","); got != "image,video,article" {
		t.Errorf("declaring a retired member changed the closed set to %q", got)
	}
}

// 解析不出来的记录一律是 error，不是被丢掉的记录：静默忽略等于让一个退役取值
// 白拿它并不具备的 canonical 身份。
func TestRetiredEnumValuesFailClosedOnUnresolvableRecords(t *testing.T) {
	t.Parallel()

	for name, body := range map[string]string{
		"unknown enum": `enums:
  ContentType: [image]
retired_enum_values:
  - {enum: MediaType, retired_value: retired_member}
`,
		"blank value": `enums:
  ContentType: [image]
retired_enum_values:
  - {enum: ContentType, retired_value: '  '}
`,
		"missing enum binding": `enums:
  ContentType: [image]
retired_enum_values:
  - {retired_value: retired_member}
`,
		"missing retired value": `enums:
  ContentType: [image]
retired_enum_values:
  - {enum: ContentType}
`,
		"extra key smuggles more than a retirement": `enums:
  ContentType: [image]
retired_enum_values:
  - {enum: ContentType, retired_value: retired_member, accept_on_wire: true}
`,
		"mapping instead of records": `enums:
  ContentType: [image]
retired_enum_values:
  ContentType: [retired_member]
`,
	} {
		t.Run(name, func(t *testing.T) {
			path := writeSharedTypes(t, body)
			_, _, err := loadSharedDefinitions(
				filepath.Dir(filepath.Dir(path)),
				path,
				ast.EnumOwnerGlobal,
				"",
			)
			if err == nil {
				t.Fatal("loadSharedDefinitions() accepted an unresolvable retired_enum_values record")
			}
			if !strings.Contains(err.Error(), "retired_enum_values") {
				t.Errorf("error %v does not name the offending section", err)
			}
		})
	}
}

// 没有声明段的文档与今天完全一致：这条路径不能因为新槽位的存在而变化。
func TestSharedTypesWithoutRetiredDeclarationStayUnchanged(t *testing.T) {
	t.Parallel()

	path := writeSharedTypes(t, "enums:\n  ContentType: [image, video]\n")
	enums, _, err := loadSharedDefinitions(
		filepath.Dir(filepath.Dir(path)),
		path,
		ast.EnumOwnerGlobal,
		"",
	)
	if err != nil {
		t.Fatalf("loadSharedDefinitions() error = %v", err)
	}
	if len(enums) != 1 || enums[0].RetiredValues != nil {
		t.Fatalf("enums = %#v, want one definition with no retired values", enums)
	}
}

// canonical 声明必须真的进到图里：仓内 ContentType 的退役成员既要被加载，也不得
// 和合法闭集重叠。
func TestRepositorySharedTypesDeclareRetiredContentTypeOutsideClosedSet(t *testing.T) {
	t.Parallel()

	metadataDir := filepath.Join(repositoryRoot(t), "quwoquan_service", "contracts", "metadata")
	enums, _, err := loadSharedDefinitions(
		metadataDir,
		filepath.Join(metadataDir, "_shared", "types.yaml"),
		ast.EnumOwnerGlobal,
		"",
	)
	if err != nil {
		t.Fatalf("loadSharedDefinitions() error = %v", err)
	}
	var contentType *ast.EnumDefinition
	for index := range enums {
		if enums[index].Name == "ContentType" {
			contentType = &enums[index]
		}
	}
	if contentType == nil {
		t.Fatal("ContentType is not declared in _shared/types.yaml")
	}
	if len(contentType.RetiredValues) == 0 {
		t.Fatal("ContentType declares no retired member; this test must not pass vacuously")
	}
	for _, retired := range contentType.RetiredValues {
		for _, live := range contentType.Values {
			if retired == live {
				t.Errorf("retired value %q is still in the ContentType closed set", retired)
			}
		}
	}
}

func repositoryRoot(t *testing.T) string {
	t.Helper()
	dir, err := os.Getwd()
	if err != nil {
		t.Fatalf("getwd: %v", err)
	}
	for {
		if _, err := os.Stat(filepath.Join(dir, "quwoquan_service", "contracts", "metadata")); err == nil {
			return dir
		}
		parent := filepath.Dir(dir)
		if parent == dir {
			t.Fatal("unable to locate repository root")
		}
		dir = parent
	}
}
