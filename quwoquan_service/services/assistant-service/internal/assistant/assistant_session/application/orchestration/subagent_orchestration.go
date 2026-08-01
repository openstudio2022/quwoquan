package orchestration

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"strings"

	assistantgenerated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
	skillpkg "quwoquan_service/services/assistant-service/internal/assistant/assistant_session/application/skill"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/domain/assistant"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/domain/ports"
)

const (
	subagentRolePrimary      = "primary"
	subagentRoleSupporting   = "supporting"
	maxSubagentPlans         = 3
	defaultSubagentTimeoutMs = 12000
)

// SubagentPlan 是并行子代理的隔离契约，形状对齐 _shared/subagent_plan：每个子代理只拿到
// 自己的目标、工具白名单、工具预算与超时。
type SubagentPlan struct {
	SubagentID      string
	SkillID         string
	DomainID        string
	ProblemClass    string
	Goal            string
	Role            string
	MaxIterations   int
	ToolBudget      int
	ToolWhitelist   []string
	SearchIntensity string
	TimeoutMs       int
}

// SubagentPlanner 判定该问题是单技能还是多技能。返回少于两条计划时按单技能执行。
type SubagentPlanner interface {
	PlanSubagents(
		ctx context.Context,
		turn assistant.AssistantTurn,
		primary SkillSelection,
	) ([]SubagentPlan, error)
}

// ModelSubagentPlanner 只在主技能声明为复杂推理时多花一次模型调用做拆分判定；其余问题
// 类型直接走单技能，避免每轮都为编排付延迟。
type ModelSubagentPlanner struct {
	Model  ModelProvider
	Loader skillpkg.Loader
}

func (planner ModelSubagentPlanner) PlanSubagents(
	ctx context.Context,
	turn assistant.AssistantTurn,
	primary SkillSelection,
) ([]SubagentPlan, error) {
	if planner.Model == nil {
		return nil, nil
	}
	problemClass, parseErr := assistantgenerated.ParseProblemClass(
		strings.ToLower(strings.TrimSpace(primary.ProblemClass)),
	)
	if parseErr != nil {
		return nil, fmt.Errorf(
			"invalid primary problemClass %q: %w",
			primary.ProblemClass,
			parseErr,
		)
	}
	if problemClass != assistantgenerated.ProblemClassComplexReasoning {
		return nil, nil
	}
	question := strings.TrimSpace(turn.Input.Text)
	if question == "" {
		return nil, nil
	}
	loader := planner.Loader
	if loader == nil {
		loader = assistantDomainSkillCatalogLoader{}
	}
	catalog, err := loader.Load()
	if err != nil {
		return nil, err
	}

	policyTools, err := canonicalToolPolicy(turn.FrozenPolicySelection.Template.AllowedTools)
	if err != nil {
		return nil, err
	}
	candidates := subagentCandidates(reactiveSkillCatalog(catalog), policyTools)
	if len(candidates) < 2 {
		return nil, nil
	}
	response, err := planner.Model.Complete(ctx, frozenPolicyModelRequest(turn, primary, ModelRequest{
		TurnID:               turn.TurnID,
		TraceID:              turn.TraceID,
		SkillID:              primary.SkillID,
		Stage:                string(ports.ModelStageOrchestration),
		Prompt:               buildSubagentPlanPrompt(candidates),
		UserQuestion:         question,
		ContextTurns:         turn.ContextTurns,
		ContextSummary:       turn.ContextSummary,
		PageContext:          turn.PageContext,
		IntersectionEvidence: turn.IntersectionEvidence,
		ContextAssembly:      primary.ContextAssembly,
		SkillCatalog:         candidates,
	}))
	if err != nil {
		// 编排判定失败不阻断运行：退回单技能仍然能回答问题。
		log.Printf("assistant agent subagent_plan_failed turnId=%s err=%v", turn.TurnID, err)
		return nil, nil
	}
	shape, plans := subagentPlansFromModel(response, candidates, policyTools)
	if shape != assistantgenerated.ProblemShapeMultiSkill || len(plans) < 2 {
		return nil, nil
	}
	log.Printf(
		"assistant agent subagent_plan_selected turnId=%s plans=%d",
		turn.TurnID,
		len(plans),
	)
	return plans, nil
}

// subagentCandidates 只保留在冻结策略工具集合内还能做事的技能。
func subagentCandidates(
	catalog []skillpkg.Manifest,
	policyTools []string,
) []skillpkg.Manifest {
	candidates := make([]skillpkg.Manifest, 0, len(catalog))
	for _, manifest := range catalog {
		if len(subagentToolWhitelist(manifest, policyTools)) == 0 {
			continue
		}
		candidates = append(candidates, manifest)
	}
	return candidates
}

// subagentToolWhitelist 是清单工具与策略允许工具的交集：清单决定该技能会用什么，策略
// 决定这一轮允许什么，两者都不能被子代理绕过。
func subagentToolWhitelist(
	manifest skillpkg.Manifest,
	policyTools []string,
) []string {
	manifestTools := manifest.ToolPolicy.PreferredTools
	if len(manifestTools) == 0 {
		manifestTools = manifest.ToolPolicy.AllowedTools
	}
	if len(policyTools) == 0 {
		// 策略不开放工具时子代理也不得自带工具。
		return nil
	}
	allowed := map[string]bool{}
	for _, name := range policyTools {
		allowed[name] = true
	}
	whitelist := []string{}
	for _, name := range manifestTools {
		if allowed[name] {
			whitelist = append(whitelist, name)
		}
	}
	return whitelist
}

func subagentPlansFromModel(
	response ModelResponse,
	candidates []skillpkg.Manifest,
	policyTools []string,
) (assistantgenerated.ProblemShape, []SubagentPlan) {
	delta := response.StructuredDelta
	if len(delta) == 0 && strings.TrimSpace(response.Text) != "" {
		parsed := map[string]any{}
		if err := json.Unmarshal([]byte(response.Text), &parsed); err == nil {
			delta = parsed
		}
	}
	shape, err := assistantgenerated.ParseProblemShape(
		strings.TrimSpace(fmtAny(delta["problemShape"])),
	)
	if err != nil {
		return assistantgenerated.ProblemShapeUnknown, nil
	}
	entries, ok := delta["subagentPlan"].([]any)
	if !ok {
		return shape, nil
	}
	byID := map[string]skillpkg.Manifest{}
	for _, manifest := range candidates {
		byID[manifest.SkillID] = manifest
	}
	plans := []SubagentPlan{}
	seen := map[string]bool{}
	for _, rawEntry := range entries {
		entry, ok := rawEntry.(map[string]any)
		if !ok {
			continue
		}
		skillID := strings.TrimSpace(fmtAny(entry["skillId"]))
		manifest, known := byID[skillID]
		if !known || seen[skillID] {
			continue
		}
		seen[skillID] = true
		plans = append(plans, subagentPlanFrom(len(plans), manifest, entry, policyTools))
		if len(plans) == maxSubagentPlans {
			break
		}
	}
	if len(plans) > 0 {
		ensureSinglePrimary(plans)
	}
	return shape, plans
}

func subagentPlanFrom(
	index int,
	manifest skillpkg.Manifest,
	entry map[string]any,
	policyTools []string,
) SubagentPlan {
	toolBudget := manifest.ToolPolicy.MaxToolCalls
	if toolBudget <= 0 {
		toolBudget = 1
	}
	role := strings.TrimSpace(fmtAny(entry["role"]))
	if role != subagentRolePrimary {
		role = subagentRoleSupporting
	}
	return SubagentPlan{
		SubagentID:    fmt.Sprintf("subagent:%d:%s", index+1, manifest.SkillID),
		SkillID:       manifest.SkillID,
		DomainID:      manifest.DomainID,
		ProblemClass:  manifest.ProblemClass,
		Goal:          strings.TrimSpace(fmtAny(entry["goal"])),
		Role:          role,
		ToolBudget:    toolBudget,
		MaxIterations: toolBudget + 1,
		ToolWhitelist: subagentToolWhitelist(manifest, policyTools),
		TimeoutMs:     defaultSubagentTimeoutMs,
	}
}

// ensureSinglePrimary 保证聚合时有唯一的主答复归属，避免多个子代理都自称 primary。
func ensureSinglePrimary(plans []SubagentPlan) {
	primary := -1
	for index := range plans {
		if plans[index].Role == subagentRolePrimary {
			if primary < 0 {
				primary = index
				continue
			}
			plans[index].Role = subagentRoleSupporting
		}
	}
	if primary < 0 {
		plans[0].Role = subagentRolePrimary
	}
}

func buildSubagentPlanPrompt(candidates []skillpkg.Manifest) string {
	var b strings.Builder
	b.WriteString("候选技能如下，判断这个问题需要几个子任务并行完成。\n")
	for _, manifest := range candidates {
		b.WriteString("- ")
		b.WriteString(manifest.SkillID)
		b.WriteString(": ")
		b.WriteString(manifest.DisplayName)
		if description := strings.TrimSpace(manifest.Description); description != "" {
			b.WriteString(" — ")
			b.WriteString(description)
		}
		b.WriteString("\n")
	}
	return b.String()
}
