// spec_ref: specs/feature-tree/object-homepage-network/intersection-unified-experience/spec.md#req-009
// spec_ref: specs/feature-tree/assistant-run-learning/spec.md
package skill_package_release_test

import (
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"

	packageasset "quwoquan_service/services/assistant-service/internal/assistant/skill_package_release/application/packageasset"
)

// 小趣撮合环 skill 策略契约：
// - capability.gathering_coordinator 放行 intersection.read_mine（撮合起点，
//   与 gathering.propose_create_draft 同一 skill 内成环）；
// - catalog consentScopes 是 contextProfile 的同源投影（context.none → 空），
//   工具级 consent（content.intersection.mine.read）由工具目录 capability 的
//   recheckAtExecution 在执行时校验，不在 skill catalog 层重复登记；
//   数据使用披露经 dataUseSummary 文案承载；
// - 官方 profile 资产 digest 与内容同源（防手改资产漂移）。

func loadOfficialProfiles(t *testing.T) packageasset.ProfileAssetCatalog {
	t.Helper()
	root := "../../../../resources/skill_packages/official/profiles"
	entries, err := os.ReadDir(root)
	if err != nil {
		t.Fatalf("read official profiles: %v", err)
	}
	catalog := packageasset.ProfileAssetCatalog{}
	for _, entry := range entries {
		raw, err := os.ReadFile(filepath.Join(root, entry.Name()))
		if err != nil {
			t.Fatalf("read %s: %v", entry.Name(), err)
		}
		var part packageasset.ProfileAssetCatalog
		if err := json.Unmarshal(raw, &part); err != nil {
			t.Fatalf("unmarshal %s: %v", entry.Name(), err)
		}
		catalog.CatalogProfiles = append(catalog.CatalogProfiles, part.CatalogProfiles...)
		catalog.ActivationProfiles = append(catalog.ActivationProfiles, part.ActivationProfiles...)
		catalog.InputProfiles = append(catalog.InputProfiles, part.InputProfiles...)
		catalog.ContextProfiles = append(catalog.ContextProfiles, part.ContextProfiles...)
		catalog.CapabilityProfiles = append(catalog.CapabilityProfiles, part.CapabilityProfiles...)
		catalog.OrchestrationProfiles = append(catalog.OrchestrationProfiles, part.OrchestrationProfiles...)
		catalog.TriggerProfiles = append(catalog.TriggerProfiles, part.TriggerProfiles...)
		catalog.MemoryProfiles = append(catalog.MemoryProfiles, part.MemoryProfiles...)
		catalog.PresentationProfiles = append(catalog.PresentationProfiles, part.PresentationProfiles...)
		catalog.EvaluationProfiles = append(catalog.EvaluationProfiles, part.EvaluationProfiles...)
	}
	return catalog
}

func TestGatheringCoordinatorAllowsIntersectionReadMine(t *testing.T) {
	catalog := loadOfficialProfiles(t)
	if err := catalog.Validate(); err != nil {
		t.Fatalf("official profile assets must stay digest-consistent: %v", err)
	}

	var capability *packageasset.CapabilityProfile
	for index := range catalog.CapabilityProfiles {
		if catalog.CapabilityProfiles[index].ProfileID == "capability.gathering_coordinator" {
			capability = &catalog.CapabilityProfiles[index]
			break
		}
	}
	if capability == nil {
		t.Fatal("capability.gathering_coordinator profile is missing")
	}
	allowed := false
	for _, toolName := range capability.ToolPolicy.AllowedTools {
		if toolName == "intersection.read_mine" {
			allowed = true
			break
		}
	}
	if !allowed {
		t.Fatal("gathering_coordinator must allow intersection.read_mine (撮合起点)")
	}

	var found bool
	for _, profile := range catalog.CatalogProfiles {
		if profile.ProfileID != "catalog.gathering_coordinator" {
			continue
		}
		found = true
		// consentScopes 是 contextProfile 同源投影（context.none → 空集），
		// 数据使用披露由 dataUseSummary 承载：必须提到交集读取事实。
		if len(profile.ConsentScopes) != 0 {
			t.Fatalf(
				"catalog consent scopes must mirror context profile (context.none): %+v",
				profile.ConsentScopes,
			)
		}
		if !strings.Contains(profile.DataUseSummary, "交集") {
			t.Fatalf(
				"data use summary must disclose intersection read: %q",
				profile.DataUseSummary,
			)
		}
	}
	if !found {
		t.Fatal("catalog.gathering_coordinator profile is missing")
	}
}
