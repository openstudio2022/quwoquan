// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/tool-fabric-runtime/spec.md#gwt-002
package local_contract

import (
	"context"
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/application/orchestration"
	toolpkg "quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/application/tool"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/domain/assistant"
	modeldouble "quwoquan_service/services/assistant-service/tests/support/modeldouble"
	"quwoquan_service/services/assistant-service/tests/support/promptassets"
)

// 技能 manifest 声明的工具必须都能装配出实现，否则模型选中后必然工具失败。
func TestSkillManifestToolPolicyIsRegistrySubset(t *testing.T) {
	catalog, err := orchestration.LoadAssistantDomainSkillCatalog()
	if err != nil {
		t.Fatalf("load assistant domain skill catalog: %v", err)
	}
	registered := map[string]bool{}
	for _, name := range toolpkg.CanonicalToolNames() {
		registered[name] = true
	}
	for _, manifest := range catalog {
		for _, name := range manifest.ToolPolicy.AllowedTools {
			if !registered[name] {
				t.Fatalf(
					"skill %q allows tool %q outside registry %v",
					manifest.SkillID,
					name,
					toolpkg.CanonicalToolNames(),
				)
			}
		}
		for _, name := range manifest.ToolPolicy.PreferredTools {
			if !toolPolicyContains(manifest.ToolPolicy.AllowedTools, name) {
				t.Fatalf(
					"skill %q prefers tool %q outside its allowedTools %v",
					manifest.SkillID,
					name,
					manifest.ToolPolicy.AllowedTools,
				)
			}
		}
	}
}

// 目录加载必须对不存在的工具名 fail-fast，而不是留到运行时才失败。
func TestSkillCatalogRejectsUnregisteredTool(t *testing.T) {
	root := t.TempDir()
	writeProbeSkillManifest(t, root, "fallback_general_search", []string{"web_search"})
	writeProbeSkillManifest(t, root, "probe_skill", []string{"web_search", "web_fetch"})
	t.Setenv("ASSISTANT_RESOURCE_ROOT", root)

	_, err := orchestration.LoadAssistantDomainSkillCatalog()
	if err == nil {
		t.Fatal("expected unregistered tool to be rejected")
	}
	if !strings.Contains(err.Error(), "web_fetch") {
		t.Fatalf("error should name the unregistered tool, got %v", err)
	}
}

// 已发布策略里的未知工具不得进入 ToolExecutionGuard；空允许集在 guard 里等于放开全部，
// 所以必须在冻结策略入口拦住。
func TestFrozenPolicyRejectsUnregisteredTool(t *testing.T) {
	registry := toolpkg.BaseRegistry()
	registry.Register(
		toolpkg.WebSearchMetadata(),
		func(_ context.Context, _ toolpkg.Request) (toolpkg.Result, error) {
			return toolpkg.Result{Output: map[string]any{
				"summary":    "杭州明天多云，适合出门。",
				"references": []any{},
			}}, nil
		},
	)
	loop := orchestration.NewAgentLoop(
		nil,
		orchestration.ReactRuntime{
			Model: modeldouble.DeterministicModelProvider{},
			Tools: orchestration.DefaultToolCoordinator{Registry: registry},
		},
		nil,
	)
	loop.PromptAssets = promptassets.MustResolver(t)
	turn := unregisteredToolPolicyTurn([]string{"app_search", "scheduler"})
	_, failure, err := loop.RunTurn(t.Context(), turn)
	if err == nil && failure == nil {
		t.Fatal("expected unregistered policy tool to fail the turn")
	}

	allowed := unregisteredToolPolicyTurn([]string{"web_search"})
	if _, failure, err := loop.RunTurn(t.Context(), allowed); err != nil || failure != nil {
		t.Fatalf("registered policy tool must run: failure=%+v err=%v", failure, err)
	}
}

func unregisteredToolPolicyTurn(allowedTools []string) assistant.AssistantTurn {
	selection := testFrozenPolicySelection("assistant-default", "fallback_general_search", "assistant")
	selection.Template.AllowedTools = allowedTools
	return assistant.AssistantTurn{
		ConversationID:        "conversation-tool-policy",
		TurnID:                "turn-tool-policy",
		TraceID:               "trace-tool-policy",
		Input:                 assistant.AssistantTurnInput{Text: "杭州明天适合出门吗"},
		FrozenPolicySelection: selection,
	}
}

// 策略发布物同样只能引用装配目录内的工具，并且模板技能必须存在于技能目录。
func TestPolicyReleaseArtifactsStayWithinToolAndSkillCatalog(t *testing.T) {
	artifacts, err := filepath.Glob(filepath.Join(
		policyArtifactRoot(t), "assistant", "*", "releases", "*.json",
	))
	if err != nil {
		t.Fatalf("glob policy release artifacts: %v", err)
	}
	if len(artifacts) == 0 {
		t.Fatal("no policy release artifact found")
	}
	catalog, err := orchestration.LoadAssistantDomainSkillCatalog()
	if err != nil {
		t.Fatalf("load assistant domain skill catalog: %v", err)
	}
	knownSkills := map[string]bool{}
	for _, manifest := range catalog {
		knownSkills[manifest.SkillID] = true
	}
	registered := map[string]bool{}
	for _, name := range toolpkg.CanonicalToolNames() {
		registered[name] = true
	}
	referenced := map[string]bool{}
	for _, path := range artifacts {
		raw, err := os.ReadFile(path)
		if err != nil {
			t.Fatalf("read %s: %v", path, err)
		}
		var artifact struct {
			Release struct {
				Templates []struct {
					TemplateID   string   `json:"templateId"`
					SkillID      string   `json:"skillId"`
					AllowedTools []string `json:"allowedTools"`
				} `json:"templates"`
			} `json:"release"`
		}
		if err := json.Unmarshal(raw, &artifact); err != nil {
			t.Fatalf("decode %s: %v", path, err)
		}
		if !referencedByEnvironment(t, path) {
			continue
		}
		referenced[path] = true
		for _, template := range artifact.Release.Templates {
			if !knownSkills[template.SkillID] {
				t.Fatalf(
					"%s template %s references unknown skill %q",
					filepath.Base(path),
					template.TemplateID,
					template.SkillID,
				)
			}
			for _, name := range template.AllowedTools {
				if !registered[name] {
					t.Fatalf(
						"%s template %s allows unregistered tool %q; registered tools are %v",
						filepath.Base(path),
						template.TemplateID,
						name,
						toolpkg.CanonicalToolNames(),
					)
				}
			}
		}
	}
	if len(referenced) == 0 {
		t.Fatal("no policy release artifact is referenced by a non-alpha environment")
	}
}

// referencedByEnvironment 只校验四环境实际引用的发布物。历史版本按不可变契约保留，不再
// 承担新工具目录的约束。
func referencedByEnvironment(t *testing.T, artifactPath string) bool {
	t.Helper()
	serviceRoot := filepath.Dir(filepath.Dir(policyArtifactRoot(t)))
	needle := filepath.Base(artifactPath)
	for _, environment := range []string{"beta", "gamma", "prod"} {
		raw, err := os.ReadFile(filepath.Join(
			serviceRoot, "environments", environment, "config.yaml",
		))
		if err != nil {
			t.Fatalf("read %s config: %v", environment, err)
		}
		if strings.Contains(string(raw), "releases/"+needle) {
			return true
		}
	}
	return false
}

func policyArtifactRoot(t *testing.T) string {
	t.Helper()
	candidates := []string{
		filepath.Join("resources", "policies"),
		filepath.Join("..", "..", "..", "..", "resources", "policies"),
	}
	for _, candidate := range candidates {
		if info, err := os.Stat(candidate); err == nil && info.IsDir() {
			absolute, err := filepath.Abs(candidate)
			if err != nil {
				t.Fatalf("resolve policy artifact root: %v", err)
			}
			return absolute
		}
	}
	t.Fatal("policy artifact root not found")
	return ""
}

func writeProbeSkillManifest(t *testing.T, root string, skillID string, allowedTools []string) {
	t.Helper()
	dir := filepath.Join(root, skillID)
	if err := os.MkdirAll(dir, 0o755); err != nil {
		t.Fatalf("create probe skill dir: %v", err)
	}
	manifest := map[string]any{
		"skillId":         skillID,
		"displayName":     skillID,
		"description":     "契约测试用探针技能",
		"domainId":        "general",
		"executionTarget": "cloud",
		"problemClass":    "general",
		"toolPolicy": map[string]any{
			"allowedTools":   allowedTools,
			"preferredTools": allowedTools[:1],
			"maxToolCalls":   2,
		},
	}
	raw, err := json.Marshal(manifest)
	if err != nil {
		t.Fatalf("encode probe skill manifest: %v", err)
	}
	if err := os.WriteFile(filepath.Join(dir, "manifest.json"), raw, 0o644); err != nil {
		t.Fatalf("write probe skill manifest: %v", err)
	}
}

func toolPolicyContains(names []string, target string) bool {
	for _, name := range names {
		if name == target {
			return true
		}
	}
	return false
}
