package validate

import (
	"testing"

	"quwoquan_service/internal/metadata/ast"
	"quwoquan_service/internal/metadata/graph"
)

func retiredValueGraph(retired []string) *graph.ContractGraph {
	return &graph.ContractGraph{Governance: ast.MetadataGovernance{
		Enums: []ast.EnumDefinition{{
			Name:          "ContentType",
			Values:        []string{"image", "video", "article"},
			RetiredValues: retired,
			OwnerLevel:    ast.EnumOwnerGlobal,
			SourcePath:    "_shared/types.yaml",
		}},
		EnumReferences: []ast.EnumReference{{
			Name:       "ContentType",
			Domain:     "content",
			ObjectID:   "content.post",
			SourcePath: "content/content/post/fields.yaml",
		}},
	}}
}

// 声明一个退役成员不改变任何既有 enum 判据：合法闭集仍然完整，也不产生新 issue。
// spec_ref: specs/feature-tree/discovery-content/content-type-framework/spec.md#req-001
func TestRetiredEnumValueOutsideClosedSetRaisesNoIssue(t *testing.T) {
	assertGovernanceIssueCodes(
		t,
		validateEnumGovernance(retiredValueGraph([]string{"retired_member"})),
	)
}

// 退役成员回到合法闭集里就是把它放回读写通道，必须 fail-closed。
// spec_ref: specs/feature-tree/discovery-content/content-type-framework/spec.md#sit-003
func TestRetiredEnumValueInsideClosedSetIsRejected(t *testing.T) {
	assertGovernanceIssueCodes(
		t,
		validateEnumGovernance(retiredValueGraph([]string{"article"})),
		"CONTRACT.ENUM.RETIRED_VALUE_STILL_LIVE",
	)
}

// 空白与重复声明都无法指向一个 exact 迁移输入。
func TestRetiredEnumValueBlankAndDuplicateAreRejected(t *testing.T) {
	assertGovernanceIssueCodes(
		t,
		validateEnumGovernance(retiredValueGraph([]string{"   "})),
		"CONTRACT.ENUM.RETIRED_VALUE_BLANK",
	)
	assertGovernanceIssueCodes(
		t,
		validateEnumGovernance(retiredValueGraph([]string{"retired_member", "retired_member"})),
		"CONTRACT.ENUM.RETIRED_VALUE_DUPLICATE",
	)
}
