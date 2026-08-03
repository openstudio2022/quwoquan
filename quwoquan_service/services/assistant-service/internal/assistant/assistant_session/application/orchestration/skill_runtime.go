package orchestration

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"log"
	"strings"

	channelpkg "quwoquan_service/services/assistant-service/internal/assistant/assistant_session/application/channel"
	contextassembly "quwoquan_service/services/assistant-service/internal/assistant/assistant_session/application/contextassembly"
	react "quwoquan_service/services/assistant-service/internal/assistant/assistant_session/application/reasoning"
	skillpkg "quwoquan_service/services/assistant-service/internal/assistant/assistant_session/application/skill"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/domain/assistant"
)

var ErrNoEligibleSkill = errors.New("no eligible assistant skill is available for this surface")

type SkillSelection struct {
	SkillID      string
	DomainID     string
	DisplayName  string
	ToolPolicy   []string
	PromptPolicy string
	// PromptAssetIDs 是清单声明的领域话术资产 ID。正文在技能被选中后由 PromptAssetResolver
	// 解析；这里只保存 ID，绝不能把 ID 本身当提示词正文送进模型。
	PromptAssetIDs  []string
	SearchIntensity string
	// ProblemClass 来自 skill manifest，是模型档位路由的输入之一。
	ProblemClass string
	// SlotSchema 声明该技能进入执行前必须具备的结构化上下文。
	SlotSchema skillpkg.SlotSchema
	// ContextProfile is resolved only for the selected Skill package.
	ContextProfile skillpkg.ContextProfile
	// ContextAssembly 是模型调用前已完成的授权上下文与槽位结果。
	ContextAssembly *contextassembly.AssemblyResult
	// MaxToolCalls 是该技能清单声明的工具预算；0 表示清单未声明，运行时退回默认预算。
	MaxToolCalls int
}

// Budget 返回该技能的执行预算。清单里的 maxToolCalls 是唯一真相源，迭代上限由它推导：
// 每次工具调用配一次规划，再留一次收尾迭代。
func (selection SkillSelection) Budget() react.Budget {
	if selection.MaxToolCalls <= 0 {
		return react.DefaultBudget()
	}
	return react.Budget{
		MaxIterations: selection.MaxToolCalls + 1,
		MaxToolCalls:  selection.MaxToolCalls,
	}
}

type SkillRuntime interface {
	SelectSkill(ctx context.Context, turn assistant.AssistantTurn) (SkillSelection, error)
}

// ScopedSkillRuntime 在给定候选集合内选择技能。集合由冻结策略能服务的技能决定，选择过程
// 只看得到集合内的技能，模型也只会拿到集合内的清单摘要。
type ScopedSkillRuntime interface {
	SelectSkillWithin(
		ctx context.Context,
		turn assistant.AssistantTurn,
		allowedSkillIDs []string,
	) (SkillSelection, error)
}

type DefaultSkillRuntime struct {
	Loader skillpkg.Loader
}

func (rt DefaultSkillRuntime) SelectSkill(
	ctx context.Context,
	turn assistant.AssistantTurn,
) (SkillSelection, error) {
	return rt.SelectSkillWithin(ctx, turn, nil)
}

func (rt DefaultSkillRuntime) SelectSkillWithin(
	ctx context.Context,
	turn assistant.AssistantTurn,
	allowedSkillIDs []string,
) (SkillSelection, error) {
	loader := rt.Loader
	if loader == nil {
		loader = skillpkg.StaticLoader{}
	}
	return ManifestSkillRuntime{
		Loader: loader,
	}.SelectSkillWithin(ctx, turn, allowedSkillIDs)
}

type ModelDrivenSkillRuntime struct {
	Model    ModelProvider
	Loader   skillpkg.Loader
	Fallback SkillRuntime
}

func (r ModelDrivenSkillRuntime) SelectSkill(
	ctx context.Context,
	turn assistant.AssistantTurn,
) (SkillSelection, error) {
	return r.SelectSkillWithin(ctx, turn, nil)
}

func (r ModelDrivenSkillRuntime) SelectSkillWithin(
	ctx context.Context,
	turn assistant.AssistantTurn,
	allowedSkillIDs []string,
) (SkillSelection, error) {
	loader := r.Loader
	if loader == nil {
		loader = skillpkg.StaticLoader{}
	}
	catalog, err := loader.Load(ctx)
	if err != nil {
		return SkillSelection{}, err
	}
	if manifest, found := manifestByID(catalog, turn.SkillID); found && manifest.IsProactive() {
		return selectionFromManifest(manifest), nil
	}
	catalog = restrictSkillCatalog(reactiveSkillCatalog(catalog), allowedSkillIDs)
	if allowedSkillIDs != nil && len(catalog) == 0 {
		return SkillSelection{}, ErrNoEligibleSkill
	}
	if manifest, ok := manifestByExplicitIDOrHint(catalog, turn); ok {
		log.Printf("assistant skill selector manifest_selected turnId=%s skillId=%s", turn.TurnID, manifest.SkillID)
		return selectionFromManifest(manifest), nil
	}
	model := r.Model
	if model != nil && strings.TrimSpace(turn.Input.Text) != "" {
		routingAssembly, assemblyErr := contextassembly.NewContextOrchestrator().
			Assemble(ctx, contextassembly.AssemblyInput{
				Turn:     turn,
				Client:   contextassembly.ClientContext{SurfaceID: turn.RequestContext.SurfaceID},
				DomainID: turn.DomainID,
				Channel: channelpkg.ResolveForSurface(
					turn.TurnType,
					turn.Trigger,
					turn.RequestContext.SurfaceKind,
				),
			})
		if assemblyErr != nil {
			return SkillSelection{}, assemblyErr
		}
		resp, err := model.Complete(ctx, ModelRequest{
			TurnID:               turn.TurnID,
			TraceID:              turn.TraceID,
			Stage:                "skill_selection",
			Prompt:               buildSkillSelectionPrompt(catalog),
			UserQuestion:         turn.Input.Text,
			ContextTurns:         turn.ContextTurns,
			ContextSummary:       turn.ContextSummary,
			PageContext:          turn.PageContext,
			IntersectionEvidence: turn.IntersectionEvidence,
			ContextAssembly:      &routingAssembly,
			FeedbackContext:      turn.FeedbackContextSnapshot,
			SkillCatalog:         catalog,
		})
		if err == nil {
			if manifest, ok := manifestByModelSelection(catalog, resp); ok {
				log.Printf("assistant skill selector model_selected turnId=%s skillId=%s reason=%s", turn.TurnID, manifest.SkillID, strings.TrimSpace(fmtAny(resp.StructuredDelta["reason"])))
				return selectionFromManifest(manifest), nil
			}
			log.Printf("assistant skill selector model_unmatched turnId=%s text=%q", turn.TurnID, resp.Text)
		} else {
			log.Printf("assistant skill selector model_failed turnId=%s err=%v", turn.TurnID, err)
		}
	}
	fallback := r.Fallback
	if fallback == nil {
		fallback = ManifestSkillRuntime{Loader: skillpkg.StaticLoader{Manifests: catalog}}
	}
	var selection SkillSelection
	if allowedSkillIDs != nil {
		scopedFallback, ok := fallback.(ScopedSkillRuntime)
		if !ok {
			return SkillSelection{}, fmt.Errorf("scoped Skill fallback is not supported")
		}
		selection, err = scopedFallback.SelectSkillWithin(ctx, turn, allowedSkillIDs)
	} else {
		selection, err = fallback.SelectSkill(ctx, turn)
	}
	if err == nil {
		log.Printf("assistant skill selector degraded_fallback turnId=%s skillId=%s", turn.TurnID, selection.SkillID)
	}
	return selection, err
}

// reactiveSkillCatalog 只保留可由用户调用的 Skill。hybrid Skill 同时参与响应式路由与
// 显式订阅触发，从而保持一个用户入口和一条 AssistantRun 管线。
func reactiveSkillCatalog(catalog []skillpkg.Manifest) []skillpkg.Manifest {
	reactive := make([]skillpkg.Manifest, 0, len(catalog))
	for _, manifest := range catalog {
		if !manifest.IsReactive() {
			continue
		}
		reactive = append(reactive, manifest)
	}
	return reactive
}

// restrictSkillCatalog 把目录收窄到策略能服务的技能。nil 表示调用方没有施加限制；
// 非 nil 空集合表示当前 surface 没有可执行 Skill，必须 fail closed。策略与目录不一致
// 也返回空集合，不能退回完整目录绕过用户/管理员设置。
func restrictSkillCatalog(
	catalog []skillpkg.Manifest,
	allowedSkillIDs []string,
) []skillpkg.Manifest {
	if allowedSkillIDs == nil {
		return catalog
	}
	allowed := make(map[string]bool, len(allowedSkillIDs))
	for _, skillID := range allowedSkillIDs {
		skillID = strings.TrimSpace(skillID)
		if skillID != "" {
			allowed[skillID] = true
		}
	}
	if len(allowed) == 0 {
		return []skillpkg.Manifest{}
	}
	restricted := make([]skillpkg.Manifest, 0, len(allowed))
	for _, manifest := range catalog {
		if allowed[manifest.SkillID] {
			restricted = append(restricted, manifest)
		}
	}
	if len(restricted) == 0 {
		log.Printf(
			"assistant skill selector policy_candidates_absent_from_catalog candidates=%v",
			allowedSkillIDs,
		)
		return []skillpkg.Manifest{}
	}
	return restricted
}

func manifestByExplicitIDOrHint(catalog []skillpkg.Manifest, turn assistant.AssistantTurn) (skillpkg.Manifest, bool) {
	if len(catalog) == 0 {
		return skillpkg.Manifest{}, false
	}
	if skillID := strings.TrimSpace(turn.SkillID); skillID != "" {
		for _, manifest := range catalog {
			if manifest.SkillID == skillID {
				return manifest, true
			}
		}
	}
	input := strings.ToLower(strings.TrimSpace(turn.Input.Text))
	if input == "" {
		return skillpkg.Manifest{}, false
	}
	best := skillpkg.Manifest{}
	bestScore := 0
	bestSpecificity := 0
	for _, manifest := range catalog {
		score := 0
		specificity := 0
		for _, hint := range manifest.RoutingHints {
			normalizedHint := strings.ToLower(strings.TrimSpace(hint))
			if normalizedHint != "" && strings.Contains(input, normalizedHint) {
				score++
				specificity += len([]rune(normalizedHint))
			}
		}
		if score > bestScore || (score == bestScore && specificity > bestSpecificity) {
			best = manifest
			bestScore = score
			bestSpecificity = specificity
		}
	}
	if bestScore == 0 {
		return skillpkg.Manifest{}, false
	}
	return best, true
}

type ManifestSkillRuntime struct {
	Loader skillpkg.Loader
}

func (r ManifestSkillRuntime) SelectSkill(
	ctx context.Context,
	turn assistant.AssistantTurn,
) (SkillSelection, error) {
	return r.SelectSkillWithin(ctx, turn, nil)
}

func (r ManifestSkillRuntime) SelectSkillWithin(
	ctx context.Context,
	turn assistant.AssistantTurn,
	allowedSkillIDs []string,
) (SkillSelection, error) {
	loader := r.Loader
	if loader == nil {
		loader = skillpkg.StaticLoader{}
	}
	catalog, err := loader.Load(ctx)
	if err != nil {
		return SkillSelection{}, err
	}
	if manifest, found := manifestByID(catalog, turn.SkillID); found && manifest.IsProactive() {
		return selectionFromManifest(manifest), nil
	}
	catalog = restrictSkillCatalog(reactiveSkillCatalog(catalog), allowedSkillIDs)
	if allowedSkillIDs != nil && len(catalog) == 0 {
		return SkillSelection{}, ErrNoEligibleSkill
	}
	return selectionFromManifest(skillpkg.NewRouter(catalog).Route(turn)), nil
}

func manifestByID(catalog []skillpkg.Manifest, skillID string) (skillpkg.Manifest, bool) {
	skillID = strings.TrimSpace(skillID)
	if skillID == "" {
		return skillpkg.Manifest{}, false
	}
	for _, manifest := range catalog {
		if strings.TrimSpace(manifest.SkillID) == skillID {
			return manifest, true
		}
	}
	return skillpkg.Manifest{}, false
}

func selectionFromManifest(manifest skillpkg.Manifest) SkillSelection {
	toolPolicy := manifest.ToolPolicy.AllowedTools
	return SkillSelection{
		SkillID:        manifest.SkillID,
		DomainID:       manifest.DomainID,
		DisplayName:    manifest.DisplayName,
		ToolPolicy:     append([]string{}, toolPolicy...),
		PromptAssetIDs: append([]string{}, manifest.PromptAssets...),
		ProblemClass:   manifest.ProblemClass,
		SlotSchema:     manifest.SlotSchema,
		ContextProfile: manifest.ContextProfile,
		MaxToolCalls:   manifest.ToolPolicy.MaxToolCalls,
	}
}

func manifestByModelSelection(catalog []skillpkg.Manifest, resp ModelResponse) (skillpkg.Manifest, bool) {
	skillID := strings.TrimSpace(fmtAny(resp.StructuredDelta["skillId"]))
	if skillID == "" && strings.TrimSpace(resp.Text) != "" {
		var parsed map[string]any
		if err := json.Unmarshal([]byte(resp.Text), &parsed); err == nil {
			skillID = strings.TrimSpace(fmtAny(parsed["skillId"]))
		}
	}
	if skillID == "" {
		return skillpkg.Manifest{}, false
	}
	for _, manifest := range catalog {
		if manifest.SkillID == skillID {
			return manifest, true
		}
	}
	return skillpkg.Manifest{}, false
}

func buildSkillSelectionPrompt(catalog []skillpkg.Manifest) string {
	var b strings.Builder
	b.WriteString("Select one assistant skillId from manifests for the user query. Return JSON only: {\"skillId\":\"...\",\"reason\":\"...\"}.\n")
	for _, manifest := range catalog {
		b.WriteString("- ")
		b.WriteString(manifest.SkillID)
		b.WriteString(": ")
		b.WriteString(manifest.DisplayName)
		if strings.TrimSpace(manifest.Description) != "" {
			b.WriteString(" — ")
			b.WriteString(manifest.Description)
		}
		b.WriteString("\n")
	}
	return b.String()
}

func fmtAny(value any) string {
	if value == nil {
		return ""
	}
	return strings.TrimSpace(fmt.Sprint(value))
}
