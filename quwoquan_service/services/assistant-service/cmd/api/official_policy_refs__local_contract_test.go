// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/tool-fabric-runtime/spec.md#req-003
// 守护:官方源资产每个技能 Resolve 后的 Hook policy refs 与 DefinitionOfDone
// verifier refs 必须被生产 HookRegistry/VerifierRegistry 完整注册;声明平台
// 不具备的验证能力会让 assistant_skill_package_policies readiness 在环境
// 启动时死锁。
package bootstrap

import (
	"context"
	"testing"

	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/runruntime"
	resourcebuilder "quwoquan_service/services/assistant-service/internal/assistant/skill_catalog/infrastructure/resource"
)

func TestOfficialSkillPolicyAndVerifierRefsAreRegistered(t *testing.T) {
	bundle, err := resourcebuilder.NewSourceBuilderAt(
		"../../resources/skill_packages/official",
	).Compile(t.Context())
	if err != nil {
		t.Fatal(err)
	}
	model := runruntime.ConstrainedVerificationModelFunc(func(
		context.Context,
		runruntime.ConstrainedVerificationRequest,
	) (runruntime.ConstrainedVerificationResponse, error) {
		return runruntime.ConstrainedVerificationResponse{}, nil
	})
	registry, err := runruntime.NewProductionHookRegistry(
		model,
		runruntime.SlogHookAuditSink{},
	)
	if err != nil {
		t.Fatal(err)
	}
	for _, manifest := range bundle.ResolvedManifests {
		if err := registry.ValidatePolicyRefs(manifest.Orchestration.HookPolicyRefs); err != nil {
			t.Errorf("skill %s hook refs: %v", manifest.SkillID, err)
		}
		if err := registry.ValidateVerifierRefs(
			manifest.Orchestration.DefinitionOfDone,
			manifest.Orchestration.VerifierRefs,
		); err != nil {
			t.Errorf("skill %s verifier refs: %v", manifest.SkillID, err)
		}
	}
}
