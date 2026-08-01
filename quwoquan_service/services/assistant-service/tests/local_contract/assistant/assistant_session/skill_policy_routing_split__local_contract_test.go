// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/skill-progressive-disclosure-routing/spec.md#gwt-001
package local_contract

import (
	"context"
	"path/filepath"
	"testing"
	"time"

	releasemodel "quwoquan_service/services/assistant-service/internal/assistant/assistant_policy_release/domain/model"
	releaseresource "quwoquan_service/services/assistant-service/internal/assistant/assistant_policy_release/infrastructure/resource"
	rolloutapplication "quwoquan_service/services/assistant-service/internal/assistant/assistant_policy_rollout/application"
	rolloutmodel "quwoquan_service/services/assistant-service/internal/assistant/assistant_policy_rollout/domain/model"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/application/orchestration"
	skillpkg "quwoquan_service/services/assistant-service/internal/assistant/assistant_session/application/skill"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/domain/assistant"
)

// 用户一句话必须真实分流到垂类技能与对应模板，而不是全部落到通用兜底。
func TestPublishedPolicyRoutesVerticalsToDistinctTemplates(t *testing.T) {
	service, candidates := publishedPolicyRolloutService(t)
	if len(candidates) < 5 {
		t.Fatalf("published policy must serve the vertical skills, got %v", candidates)
	}
	runtime := orchestration.ManifestSkillRuntime{Loader: publishedSkillLoader{}}

	cases := []struct {
		text       string
		skillID    string
		templateID string
	}{
		{"帮我安排下周去杭州的行程", "travel_planning", "travel-planning"},
		{"从西湖到机场坐地铁怎么走", "travel_transport", "travel-transport"},
		{"杭州明天天气怎么样", "weather", "weather-realtime"},
		{"附近有什么适合家庭聚餐的餐厅", "local_life", "local-life"},
		{"石墨烯的导电原理是什么", "knowledge_general", "knowledge-general"},
	}
	seenTemplates := map[string]bool{}
	for _, testCase := range cases {
		selection, err := runtime.SelectSkillWithin(
			t.Context(),
			assistant.AssistantTurn{Input: assistant.AssistantTurnInput{Text: testCase.text}},
			candidates,
		)
		if err != nil {
			t.Fatalf("select skill for %q: %v", testCase.text, err)
		}
		if selection.SkillID != testCase.skillID {
			t.Fatalf("%q routed to skill %q, want %q", testCase.text, selection.SkillID, testCase.skillID)
		}
		frozen, err := service.ResolveFrozenSelection(
			t.Context(),
			"assistant-default",
			"persona-routing",
			selection.SkillID,
			selection.DomainID,
		)
		if err != nil {
			t.Fatalf("resolve frozen selection for %q: %v", testCase.skillID, err)
		}
		if frozen.Template.TemplateID != testCase.templateID {
			t.Fatalf(
				"skill %q froze template %q, want %q",
				testCase.skillID,
				frozen.Template.TemplateID,
				testCase.templateID,
			)
		}
		if frozen.Template.SkillID != testCase.skillID {
			t.Fatalf(
				"template %q serves skill %q, want %q",
				frozen.Template.TemplateID,
				frozen.Template.SkillID,
				testCase.skillID,
			)
		}
		seenTemplates[frozen.Template.TemplateID] = true
	}
	if len(seenTemplates) != len(cases) {
		t.Fatalf("verticals must not collapse into one template, got %v", seenTemplates)
	}
}

// 策略未覆盖的技能不得被选中：否则冻结时会静默回落到默认模板并丢掉用户意图。
func TestSkillSelectionStaysWithinPolicyCandidates(t *testing.T) {
	_, candidates := publishedPolicyRolloutService(t)
	runtime := orchestration.ManifestSkillRuntime{Loader: publishedSkillLoader{}}
	allowed := map[string]bool{}
	for _, skillID := range candidates {
		allowed[skillID] = true
	}
	if allowed["astrology_constellation"] {
		t.Fatal("fixture assumption broken: published policy already serves astrology_constellation")
	}

	selection, err := runtime.SelectSkillWithin(
		t.Context(),
		assistant.AssistantTurn{
			Input: assistant.AssistantTurnInput{Text: "看看我的星座运势和上升星座"},
		},
		candidates,
	)
	if err != nil {
		t.Fatalf("select skill: %v", err)
	}
	if !allowed[selection.SkillID] {
		t.Fatalf("selected skill %q is outside policy candidates %v", selection.SkillID, candidates)
	}
}

type publishedSkillLoader struct{}

func (publishedSkillLoader) Load() ([]skillpkg.Manifest, error) {
	return orchestration.LoadAssistantDomainSkillCatalog()
}

// publishedPolicyRolloutService 用四环境正在引用的发布物驱动 rollout 服务，保证测试断言的是
// 真实发布内容而不是测试自造的策略。
func publishedPolicyRolloutService(t *testing.T) (*rolloutapplication.Service, []string) {
	t.Helper()
	release := publishedRelease(t)
	store := &publishedRolloutStore{current: rolloutmodel.Rollout{
		PolicyID: release.PolicyID,
		Revision: 1,
		Status:   "active",
		BucketDefinitions: []rolloutmodel.BucketDefinition{
			{Cohort: "all", WeightBasisPoints: 10000},
		},
		Assignments: []rolloutmodel.CohortAssignment{
			{Cohort: "all", ReleaseDigest: release.ReleaseDigest},
		},
	}}
	service := rolloutapplication.NewService(
		store,
		publishedReleaseCatalog{release.ReleaseDigest: release},
		time.Now,
	)
	candidates, err := service.ResolveSkillCandidates(
		t.Context(),
		release.PolicyID,
		"persona-routing",
	)
	if err != nil {
		t.Fatalf("resolve policy skill candidates: %v", err)
	}
	return service, candidates
}

func publishedRelease(t *testing.T) releasemodel.Release {
	t.Helper()
	root := policyArtifactRoot(t)
	artifacts, err := filepath.Glob(filepath.Join(root, "assistant", "*", "releases", "*.json"))
	if err != nil {
		t.Fatalf("glob release artifacts: %v", err)
	}
	for _, path := range artifacts {
		if !referencedByEnvironment(t, path) {
			continue
		}
		reference, err := filepath.Rel(filepath.Dir(root), path)
		if err != nil {
			t.Fatalf("relative artifact reference: %v", err)
		}
		artifact, err := releaseresource.LoadReleaseArtifact(filepath.Dir(root), reference)
		if err != nil {
			t.Fatalf("load release artifact %s: %v", path, err)
		}
		return artifact.Release
	}
	t.Fatal("no release artifact is referenced by a non-alpha environment")
	return releasemodel.Release{}
}

type publishedReleaseCatalog map[string]releasemodel.Release

func (catalog publishedReleaseCatalog) Get(
	_ context.Context,
	_ string,
	releaseDigest string,
) (releasemodel.Release, bool, error) {
	release, ok := catalog[releaseDigest]
	return release, ok, nil
}

type publishedRolloutStore struct {
	current rolloutmodel.Rollout
}

func (store *publishedRolloutStore) Get(
	_ context.Context,
	policyID string,
) (rolloutmodel.Rollout, bool, error) {
	return store.current, store.current.PolicyID == policyID, nil
}

func (store *publishedRolloutStore) GetCommandResult(
	_ context.Context,
	_ string,
	_ string,
	_ string,
) (rolloutmodel.Rollout, bool, error) {
	return rolloutmodel.Rollout{}, false, nil
}

func (store *publishedRolloutStore) Commit(
	_ context.Context,
	_ string,
	_ string,
	_ int,
	next rolloutmodel.Rollout,
	_ string,
) (rolloutmodel.Rollout, bool, error) {
	store.current = next
	return next, false, nil
}
