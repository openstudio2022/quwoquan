package replay

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"strings"
	"time"

	rtfailures "quwoquan_service/runtime/failures"
	"quwoquan_service/runtime/streaming"
	assistantgenerated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
	app "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/orchestration"
	assistantstreaming "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/streaming"
	toolpkg "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/tool"
	assistant "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain/model"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain/ports"
	skillpkg "quwoquan_service/services/assistant-service/internal/assistant/skill_package_release/application/packageasset"
)

type Runner struct {
	Now          func() time.Time
	PromptAssets ports.PromptAssetResolver
	Catalog      []skillpkg.Manifest
}

type replayCatalogLoader struct {
	catalog []skillpkg.Manifest
}

func (loader replayCatalogLoader) Load(
	ctx context.Context,
) ([]skillpkg.Manifest, error) {
	if err := ctx.Err(); err != nil {
		return nil, err
	}
	if len(loader.catalog) == 0 {
		return nil, skillpkg.ErrCatalogUnavailable
	}
	return append([]skillpkg.Manifest(nil), loader.catalog...), nil
}

type Transcript struct {
	CaseID               string               `json:"caseId"`
	SelectedSkillID      string               `json:"selectedSkillId,omitempty"`
	SelectedDomainID     string               `json:"selectedDomainId,omitempty"`
	ToolCalls            []ReplayToolCall     `json:"toolCalls"`
	ClarificationSlotIDs []string             `json:"clarificationSlotIds"`
	ReferenceURLs        []string             `json:"referenceUrls"`
	FinalAnswerMode      string               `json:"finalAnswerMode,omitempty"`
	Events               []streaming.Envelope `json:"events"`
	Failure              *rtfailures.Failure  `json:"runtimeFailure,omitempty"`
}

type ReplayToolCall struct {
	ToolName string         `json:"toolName"`
	Input    map[string]any `json:"input,omitempty"`
}

func LoadCase(path string) (assistant.ReplayCase, error) {
	raw, err := os.ReadFile(path)
	if err != nil {
		return assistant.ReplayCase{}, err
	}
	var replay assistant.ReplayCase
	if err := json.Unmarshal(raw, &replay); err != nil {
		return assistant.ReplayCase{}, err
	}
	return replay, nil
}

func (r Runner) Run(ctx context.Context, replay assistant.ReplayCase) (Transcript, error) {
	now := r.now()
	manifest, trigger, err := resolveReplayExecution(replay.Request, r.Catalog)
	if err != nil {
		return Transcript{}, err
	}
	skillID := manifest.SkillID
	domainID := manifest.DomainID
	allowedTools := manifest.ToolPolicy.AllowedTools
	turn := assistant.AssistantTurn{
		TurnID:    replay.Request.TurnID,
		SessionID: replay.Request.SessionID,
		UserID:    replay.Request.UserID,
		TurnType:  "replay",
		Status:    "running",
		SkillID:   skillID,
		DomainID:  domainID,
		Input:     assistant.AssistantTurnInput{Text: replay.Request.InputText},
		Trigger:   trigger,
		TraceID:   "trace_" + replay.ReplayCaseID,
		RequestContext: assistant.AssistantRunRequestContext{
			SurfaceID: stringValue(replay.Request.ClientContext, "surfaceId", "assistant.personal"),
			PersonaID: replay.Request.UserID,
		},
		CreatedAt: now,
		FrozenPolicySelection: assistant.AssistantFrozenPolicySelection{
			PolicyID:        "assistant-replay",
			ReleaseDigest:   "ac203c9843b5bd8c883e07039ff82820c94422010be6108bb82403ca25376a22",
			Cohort:          "replay",
			RolloutRevision: 1,
			RuleID:          "replay",
			Template: assistant.AssistantFrozenPolicyTemplate{
				TemplateID:      "replay",
				SkillID:         skillID,
				DomainID:        domainID,
				PromptPolicy:    "replay",
				AllowedTools:    append([]string(nil), allowedTools...),
				SearchIntensity: "medium",
			},
		},
	}
	toolExecutor := &scriptedToolExecutor{
		now:    r.now,
		steps:  replay.FakeToolScript,
		cursor: map[string]int{},
	}
	loop := app.NewAgentLoop(
		nil,
		app.ReactRuntime{
			Model: &scriptedModelProvider{
				steps:  replay.FakeModelScript,
				cursor: map[string]int{},
			},
			Tools: toolExecutor,
		},
		r.now,
	)
	loop.Catalog = replayCatalogLoader{catalog: r.Catalog}
	loop.PromptAssets = r.PromptAssets
	events, failure, err := loop.RunTurn(ctx, turn)
	if err != nil {
		return Transcript{}, err
	}
	transcript := projectTranscript(replay.ReplayCaseID, events, toolExecutor.calls)
	transcript.Failure = failure
	if failure != nil && transcript.FinalAnswerMode == "" {
		transcript.FinalAnswerMode = "blocked"
	}
	return transcript, nil
}

// resolveReplayExecution 决定回放 Case 的执行清单与触发形状：
//   - reactive Case（未声明 proactive trigger）必须由 production Router 按输入
//     文本路由到期望技能，执行 manifest 使用路由结果而非直接信任 request.SkillID；
//   - proactive Case 必须携带与生产 Trigger→AssistantRun 相同形状的受信
//     trigger identity，缺失或不完整时 fail-closed。
func resolveReplayExecution(
	request assistant.ReplayRequest,
	catalog []skillpkg.Manifest,
) (skillpkg.Manifest, assistant.AssistantTurnTrigger, error) {
	if len(catalog) == 0 {
		return skillpkg.Manifest{}, assistant.AssistantTurnTrigger{}, fmt.Errorf(
			"replay catalog is required",
		)
	}
	skillID := strings.TrimSpace(request.SkillID)
	expected, found := catalogManifestByID(catalog, skillID)
	if !found {
		return skillpkg.Manifest{}, assistant.AssistantTurnTrigger{}, fmt.Errorf(
			"replay execution skill %q is not in production catalog",
			skillID,
		)
	}
	if domainID := strings.TrimSpace(request.DomainID); domainID != "" &&
		domainID != expected.DomainID {
		return skillpkg.Manifest{}, assistant.AssistantTurnTrigger{}, fmt.Errorf(
			"replay execution domain %q does not match skill %q",
			domainID,
			skillID,
		)
	}
	switch strings.TrimSpace(request.TriggerType) {
	case "":
		return resolveReactiveReplayExecution(request, expected, catalog)
	case skillpkg.ReplayTriggerTypeProactive:
		return resolveProactiveReplayExecution(request, expected)
	default:
		return skillpkg.Manifest{}, assistant.AssistantTurnTrigger{}, fmt.Errorf(
			"replay execution trigger type %q is not supported",
			request.TriggerType,
		)
	}
}

func resolveReactiveReplayExecution(
	request assistant.ReplayRequest,
	expected skillpkg.Manifest,
	catalog []skillpkg.Manifest,
) (skillpkg.Manifest, assistant.AssistantTurnTrigger, error) {
	if !expected.IsReactive() {
		return skillpkg.Manifest{}, assistant.AssistantTurnTrigger{}, fmt.Errorf(
			"replay execution skill %q is proactive-only and requires a trusted trigger identity",
			expected.SkillID,
		)
	}
	if request.TrustedTriggerIdentity != nil {
		return skillpkg.Manifest{}, assistant.AssistantTurnTrigger{}, fmt.Errorf(
			"reactive replay case must not carry a trusted trigger identity",
		)
	}
	// 与生产 skillSelectionForTurn 相同的候选收窄：只有用户可调用的
	// Skill 参与输入路由；路由探针不携带 SkillID，避免精确匹配绕过路由。
	routed := skillpkg.NewRouter(reactiveCatalog(catalog)).Route(assistant.AssistantTurn{
		Input: assistant.AssistantTurnInput{Text: request.InputText},
	})
	if routed.SkillID != expected.SkillID {
		return skillpkg.Manifest{}, assistant.AssistantTurnTrigger{}, fmt.Errorf(
			"production router selected skill %q for input %q, replay case expects %q",
			routed.SkillID,
			request.InputText,
			expected.SkillID,
		)
	}
	return routed, assistant.AssistantTurnTrigger{Type: "replay"}, nil
}

func resolveProactiveReplayExecution(
	request assistant.ReplayRequest,
	expected skillpkg.Manifest,
) (skillpkg.Manifest, assistant.AssistantTurnTrigger, error) {
	if !expected.IsProactive() {
		return skillpkg.Manifest{}, assistant.AssistantTurnTrigger{}, fmt.Errorf(
			"replay execution skill %q does not accept proactive triggers",
			expected.SkillID,
		)
	}
	envelope, err := trustedTriggerEnvelope(request.TrustedTriggerIdentity)
	if err != nil {
		return skillpkg.Manifest{}, assistant.AssistantTurnTrigger{}, err
	}
	return expected, assistant.AssistantTurnTrigger{
		Type:     proactiveTurnTriggerType(envelope.Kind),
		Envelope: &envelope,
	}, nil
}

// trustedTriggerEnvelope 按 triggerruntime.Dispatcher 的 Envelope 校验口径
// 验证受信 trigger identity；任何字段缺失或非法都必须 fail-closed。
func trustedTriggerEnvelope(
	identity *assistant.AssistantTriggerEnvelope,
) (assistant.AssistantTriggerEnvelope, error) {
	if identity == nil {
		return assistant.AssistantTriggerEnvelope{}, fmt.Errorf(
			"proactive replay case requires a trusted trigger identity",
		)
	}
	envelope := *identity
	if _, err := assistantgenerated.ParseAssistantTriggerKind(
		strings.TrimSpace(envelope.Kind),
	); err != nil ||
		strings.TrimSpace(envelope.TriggerID) == "" ||
		envelope.OccurredAt.IsZero() ||
		strings.TrimSpace(envelope.SubscriptionRef) == "" ||
		strings.TrimSpace(envelope.DedupeKey) == "" ||
		strings.TrimSpace(envelope.DeliveryPolicyRef) == "" {
		return assistant.AssistantTriggerEnvelope{}, fmt.Errorf(
			"proactive replay case carries an invalid trusted trigger identity",
		)
	}
	return envelope, nil
}

// proactiveTurnTriggerType 对齐生产 proactive 触发写入的 turn trigger type：
// 订阅调度使用 "cron"，其余受信触发进入统一的 proactive 投递通道。
func proactiveTurnTriggerType(kind string) string {
	if strings.TrimSpace(kind) == string(assistantgenerated.AssistantTriggerKindSchedule) {
		return "cron"
	}
	return "proactive_delivery"
}

func catalogManifestByID(
	catalog []skillpkg.Manifest,
	skillID string,
) (skillpkg.Manifest, bool) {
	for _, manifest := range catalog {
		if manifest.SkillID == skillID {
			return manifest, true
		}
	}
	return skillpkg.Manifest{}, false
}

// reactiveCatalog 与生产路由前的候选收窄语义一致：proactive-only Skill
// 不参与用户输入路由，hybrid Skill 同时保留响应式入口。
func reactiveCatalog(catalog []skillpkg.Manifest) []skillpkg.Manifest {
	reactive := make([]skillpkg.Manifest, 0, len(catalog))
	for _, manifest := range catalog {
		if manifest.IsReactive() {
			reactive = append(reactive, manifest)
		}
	}
	return reactive
}

func projectTranscript(
	caseID string,
	events []streaming.Envelope,
	toolCalls []ReplayToolCall,
) Transcript {
	transcript := Transcript{
		CaseID:               caseID,
		ToolCalls:            append([]ReplayToolCall(nil), toolCalls...),
		ClarificationSlotIDs: []string{},
		ReferenceURLs:        []string{},
		Events:               events,
	}
	referenceURLs := map[string]bool{}
	for _, event := range events {
		if process, ok := event.Payload["process"].(assistant.AssistantRunVisibleProcess); ok {
			if process.Stage == "classifying" && process.Status == "completed" {
				transcript.SelectedSkillID = strings.TrimSpace(process.SkillID)
				transcript.SelectedDomainID = strings.TrimSpace(process.DomainID)
			}
			for _, reference := range process.AcceptedReferences {
				url := strings.TrimSpace(reference.Destination.URL)
				if url != "" && !referenceURLs[url] {
					referenceURLs[url] = true
					transcript.ReferenceURLs = append(transcript.ReferenceURLs, url)
				}
			}
		}
		if event.EventType != string(assistantstreaming.AssistantStreamEventCompleted) {
			continue
		}
		transcript.FinalAnswerMode = strings.TrimSpace(
			stringValue(event.Payload, "finalAnswerMode", ""),
		)
		if askUser, ok := event.Payload["askUser"].(map[string]any); ok {
			slotID := strings.TrimSpace(stringValue(askUser, "slotId", ""))
			if slotID != "" {
				transcript.ClarificationSlotIDs = append(
					transcript.ClarificationSlotIDs,
					slotID,
				)
			}
		}
	}
	return transcript
}

func (r Runner) now() time.Time {
	if r.Now != nil {
		return r.Now().UTC()
	}
	return time.Now().UTC()
}

// scriptedModelProvider 按 stage 顺序消费脚本步骤：同一 stage 声明多步时依序
// 返回（支持失败后重试的多轮规划），耗尽后重复最后一步以保持既有单步语义。
type scriptedModelProvider struct {
	steps  []assistant.ReplayModelStep
	cursor map[string]int
}

func (p *scriptedModelProvider) Complete(_ context.Context, req app.ModelRequest) (app.ModelResponse, error) {
	matched := make([]assistant.ReplayModelStep, 0, len(p.steps))
	for _, step := range p.steps {
		if step.Stage == req.Stage {
			matched = append(matched, step)
		}
	}
	if len(matched) > 0 {
		if p.cursor == nil {
			p.cursor = map[string]int{}
		}
		index := p.cursor[req.Stage]
		if index >= len(matched) {
			index = len(matched) - 1
		}
		p.cursor[req.Stage]++
		step := matched[index]
		return app.ModelResponse{
			Text:            step.Text,
			StructuredDelta: step.StructuredDelta,
			Usage:           step.Usage,
			FinishReason:    step.FinishReason,
		}, nil
	}
	if req.Stage == "reasoning" {
		for _, step := range p.steps {
			if step.Stage == "final" {
				return app.ModelResponse{
					Text:         step.Text,
					Usage:        step.Usage,
					FinishReason: "stop",
				}, nil
			}
		}
	}
	return app.ModelResponse{}, fmt.Errorf("replay script has no response for stage %q", req.Stage)
}

// scriptedToolExecutor 按工具名顺序消费脚本步骤：同一工具声明多步时依序返回
// （支持首次失败第二次成功的重试轨迹），耗尽后重复最后一步。
type scriptedToolExecutor struct {
	now    func() time.Time
	steps  []assistant.ReplayToolStep
	calls  []ReplayToolCall
	cursor map[string]int
}

func (*scriptedToolExecutor) ToolMetadata(
	toolName string,
) (toolpkg.Metadata, bool) {
	toolName = strings.TrimSpace(toolName)
	for _, metadata := range toolpkg.CanonicalMetadata() {
		if metadata.ToolName == toolName {
			return metadata, true
		}
	}
	return toolpkg.Metadata{}, false
}

func (e *scriptedToolExecutor) ModelToolDeclarations(
	allowedToolNames []string,
) []ports.ModelToolDefinition {
	seen := map[string]bool{}
	definitions := make([]ports.ModelToolDefinition, 0, len(allowedToolNames))
	for _, rawName := range allowedToolNames {
		name := strings.TrimSpace(rawName)
		if name == "" || seen[name] {
			continue
		}
		seen[name] = true
		metadata, available := e.ToolMetadata(name)
		if !available {
			continue
		}
		declaration := toolpkg.ModelDeclarationFor(metadata)
		definitions = append(definitions, ports.ModelToolDefinition{
			Name:        declaration.Name,
			Description: declaration.Description,
			Parameters:  declaration.Parameters,
		})
	}
	return definitions
}

func (e *scriptedToolExecutor) Execute(_ context.Context, req app.ToolRequest) (app.ToolExecution, error) {
	now := time.Now().UTC()
	if e.now != nil {
		now = e.now().UTC()
	}
	input := req.Input
	if input == nil {
		input = map[string]any{
			"query": req.Turn.Input.Text,
		}
	}
	e.calls = append(e.calls, ReplayToolCall{
		ToolName: strings.TrimSpace(req.ToolName),
		Input:    copyMap(input),
	})
	requested := assistant.ToolUse{
		// ToolUseID 带调用序号：同一 turn 内重试同一工具时保持标识唯一。
		ToolUseID: fmt.Sprintf(
			"tu_%s_%d",
			strings.ReplaceAll(req.Turn.TurnID, "atn_", ""),
			len(e.calls),
		),
		TurnID:    req.Turn.TurnID,
		ToolName:  req.ToolName,
		Placement: "cloud",
		Input:     input,
		Status:    "requested",
		CreatedAt: now,
	}
	matched := make([]assistant.ReplayToolStep, 0, len(e.steps))
	for _, step := range e.steps {
		if step.ToolName == req.ToolName {
			matched = append(matched, step)
		}
	}
	if len(matched) == 0 {
		return app.ToolExecution{}, fmt.Errorf("scripted tool %q not found", req.ToolName)
	}
	if e.cursor == nil {
		e.cursor = map[string]int{}
	}
	index := e.cursor[req.ToolName]
	if index >= len(matched) {
		index = len(matched) - 1
	}
	e.cursor[req.ToolName]++
	step := matched[index]
	completed := requested
	completedAt := now.Add(time.Millisecond)
	completed.CompletedAt = &completedAt
	if len(step.Failure) > 0 {
		failure := rtfailures.Failure{
			Code:   stringValue(step.Failure, "code", "ASSISTANT.MIDDLEWARE.tool_failed"),
			Origin: rtfailures.OriginRemoteDependency,
			Kind:   rtfailures.Kind(stringValue(step.Failure, "kind", string(rtfailures.KindUnavailable))),
			Nature: rtfailures.NatureTransient,
			Location: rtfailures.Location{
				BusinessObject: "tool_use",
				FunctionModule: "assistant_simulator",
			},
		}.Normalized()
		completed.Status = "failed"
		completed.Failure = &failure
		execution := app.ToolExecution{
			Requested: requested,
			Completed: completed,
			Failure:   &failure,
		}
		// recoveryAction 模拟该工具 metadata 声明的失败恢复合同；非法值必须
		// fail-closed，防止脚本静默退回 fail_turn。
		if action := stringValue(step.Failure, "recoveryAction", ""); action != "" {
			recovery, err := assistantgenerated.ParseToolRecoveryAction(action)
			if err != nil {
				return app.ToolExecution{}, fmt.Errorf(
					"scripted tool %q has invalid recovery action %q",
					req.ToolName,
					action,
				)
			}
			execution.RecoveryAction = recovery
		}
		return execution, nil
	}
	if strings.TrimSpace(step.Status) == "waiting_confirmation" {
		completed.Status = "waiting_confirmation"
		completed.Result = step.Result
		return app.ToolExecution{Requested: requested, Completed: completed}, nil
	}
	completed.Status = "completed"
	completed.Result = step.Result
	return app.ToolExecution{Requested: requested, Completed: completed}, nil
}

func stringValue(values map[string]any, key string, fallback string) string {
	if value, ok := values[key].(string); ok && strings.TrimSpace(value) != "" {
		return value
	}
	return fallback
}

func copyMap(source map[string]any) map[string]any {
	if source == nil {
		return nil
	}
	copied := make(map[string]any, len(source))
	for key, value := range source {
		copied[key] = value
	}
	return copied
}
