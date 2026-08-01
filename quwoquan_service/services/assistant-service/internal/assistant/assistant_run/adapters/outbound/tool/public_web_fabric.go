package tool

import (
	"context"
	"errors"
	"strings"

	publicweb "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/publicweb"
	toolpkg "quwoquan_service/services/assistant-service/internal/assistant/assistant_session/application/tool"
)

// DurableRequest is the production boundary used by an AssistantRun worker.
// RunID and SkillID are trusted worker state and always replace model-supplied
// values before schema validation or handler execution.
type DurableRequest struct {
	ToolName string
	RunID    string
	SkillID  string
	Input    map[string]any
	History  []string
}

type DurableResult struct {
	Output     map[string]any
	Assessment publicweb.EvidenceAssessment
}

// PublicWebFabric owns the executable web_search/web_open/web_find registry.
// It applies canonical metadata budgets, retries, loop detection and schemas;
// callers do not assemble individual handlers or bypass server input injection.
type PublicWebFabric struct {
	registry toolpkg.Registry
	handlers map[string]toolpkg.Handler
}

func NewPublicWebFabric(
	searchDelegate toolpkg.Handler,
	ledger publicweb.DiscoveryLedger,
	service *publicweb.Service,
	finder *publicweb.Finder,
) *PublicWebFabric {
	if searchDelegate == nil || ledger == nil || service == nil || finder == nil {
		panic("production public web fabric dependencies are required")
	}
	registry := toolpkg.BaseRegistry()
	handlers := map[string]toolpkg.Handler{
		"web_search": SearchHandler(searchDelegate, ledger),
		"web_open":   OpenHandler(service),
		"web_find":   FindHandler(finder),
	}
	registry.Register(toolpkg.WebSearchMetadata(), handlers["web_search"])
	registry.Register(toolpkg.WebOpenMetadata(), handlers["web_open"])
	registry.Register(toolpkg.WebFindMetadata(), handlers["web_find"])
	registry.RegisterDeviceAction(toolpkg.CalendarCreateReminderMetadata())
	return &PublicWebFabric{registry: registry, handlers: handlers}
}

func (f *PublicWebFabric) Execute(
	ctx context.Context,
	request DurableRequest,
) (DurableResult, error) {
	if f == nil || strings.TrimSpace(request.RunID) == "" {
		return DurableResult{}, canonicalPublicWebFailure(publicweb.ErrInvalidTarget)
	}
	input := cloneMap(request.Input)
	input["runId"] = strings.TrimSpace(request.RunID)
	switch strings.TrimSpace(request.ToolName) {
	case "web_search", "web_open":
		input["skillId"] = strings.TrimSpace(request.SkillID)
	case "web_find":
		delete(input, "skillId")
	default:
		return DurableResult{}, errors.New("unsupported public web tool")
	}
	result, err := f.registry.Execute(ctx, toolpkg.Request{
		ToolName: strings.TrimSpace(request.ToolName),
		Input:    input,
		History:  append([]string{}, request.History...),
	})
	if err != nil {
		return DurableResult{}, err
	}
	assessment, err := evidenceAssessmentFromOutput(result.Output)
	if err != nil {
		return DurableResult{}, canonicalPublicWebFailure(publicweb.ErrEvidenceUnavailable)
	}
	return DurableResult{Output: result.Output, Assessment: assessment}, nil
}

// RegisterInto supports the existing synchronous AgentLoop while the durable
// worker calls Execute directly. Both paths consume exactly the same handlers.
func (f *PublicWebFabric) RegisterInto(registry *toolpkg.Registry) {
	if f == nil || registry == nil {
		panic("public web fabric registry is required")
	}
	for _, toolName := range []string{"web_search", "web_open", "web_find"} {
		metadata, ok := f.registry.Metadata(toolName)
		if !ok {
			panic("public web fabric metadata is incomplete")
		}
		registry.Register(metadata, f.handlers[toolName])
	}
}

func evidenceAssessmentFromOutput(
	output map[string]any,
) (publicweb.EvidenceAssessment, error) {
	raw, ok := output["evidenceAssessment"].(map[string]any)
	if !ok {
		return publicweb.EvidenceAssessment{}, errors.New("public web evidence assessment is missing")
	}
	status, _ := raw["status"].(string)
	sufficient, sufficientOK := raw["evidenceSufficient"].(bool)
	replan, replanOK := raw["replanRequired"].(bool)
	reason, _ := raw["reason"].(string)
	assessment := publicweb.EvidenceAssessment{
		Status:             publicweb.EvidenceStatus(strings.TrimSpace(status)),
		EvidenceSufficient: sufficient,
		ReplanRequired:     replan,
		Reason:             strings.TrimSpace(reason),
		TargetIDs:          stringValues(raw["targetIds"]),
		DocumentIDs:        stringValues(raw["documentIds"]),
		ArtifactRefs:       stringValues(raw["artifactRefs"]),
		SourceIDs:          stringValues(raw["sourceIds"]),
	}
	if !sufficientOK || !replanOK || assessment.Status == "" || assessment.Reason == "" {
		return publicweb.EvidenceAssessment{}, errors.New("public web evidence assessment is invalid")
	}
	return assessment, nil
}

func stringValues(value any) []string {
	switch values := value.(type) {
	case []string:
		return append([]string{}, values...)
	case []any:
		result := make([]string, 0, len(values))
		for _, item := range values {
			text, _ := item.(string)
			if text = strings.TrimSpace(text); text != "" {
				result = append(result, text)
			}
		}
		return result
	default:
		return []string{}
	}
}
