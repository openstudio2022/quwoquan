package orchestration

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"
	"time"

	generated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
	presentationpkg "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/presentation"
)

func selectTemplateInput(
	schema map[string]any,
	sources []map[string]any,
) (map[string]any, bool) {
	properties, ok := schema["properties"].(map[string]any)
	if !ok {
		return nil, false
	}
	selected := make(map[string]any, len(properties))
	for name := range properties {
		for _, source := range sources {
			if value, found := source[name]; found {
				selected[name] = value
				break
			}
		}
	}
	for _, name := range stringList(schema["required"]) {
		if _, found := selected[name]; !found {
			return nil, false
		}
	}
	return selected, true
}

func toolConfirmationPresentation(
	pending map[string]any,
) (map[string]any, string, presentationpkg.ActionPolicy, error) {
	runID := executionString(pending, "runId")
	toolUseID := executionString(pending, "toolUseId")
	continuationToken := executionString(pending, "continuationToken")
	issuedAt, issuedErr := time.Parse(
		time.RFC3339Nano,
		executionString(pending, "issuedAt"),
	)
	expiresAt, expiresErr := time.Parse(
		time.RFC3339Nano,
		executionString(pending, "expiresAt"),
	)
	proposal := objectMap(pending["proposal"])
	input := objectMap(proposal["input"])
	confirmation := objectMap(proposal["confirmation"])
	toolName := executionString(proposal, "toolName")
	templateRef := executionString(confirmation, "templateRef")
	title := executionString(confirmation, "title")
	body := executionString(confirmation, "description")
	if runID == "" || toolUseID == "" || continuationToken == "" ||
		issuedErr != nil || expiresErr != nil ||
		!expiresAt.After(issuedAt) ||
		toolName == "" || templateRef == "" || title == "" ||
		body == "" || len(input) == 0 {
		return nil, "", nil, fmt.Errorf("invalid typed tool confirmation proposal")
	}
	rows := make([]any, 0)
	for _, raw := range anyList(confirmation["displayFields"]) {
		field := objectMap(raw)
		key := executionString(field, "inputKey")
		label := executionString(field, "label")
		value, found := input[key]
		if key == "" || label == "" || !found || emptyPresentationValue(value) {
			continue
		}
		text := presentationValueText(value)
		if text == "" {
			return nil, "", nil, fmt.Errorf("invalid confirmation display value")
		}
		rows = append(rows, map[string]any{"项目": label, "内容": text})
	}
	if len(rows) == 0 {
		return nil, "", nil, fmt.Errorf("typed tool confirmation has no displayable fields")
	}
	inputDigest, ok := presentationGroundingDigest(input)
	if !ok {
		return nil, "", nil, fmt.Errorf("tool confirmation input digest unavailable")
	}
	approvedContract := map[string]any{
		"runId":            runID,
		"toolInvocationId": toolUseID,
		"decision":         "approved",
		"capability":       toolName,
		"inputDigest":      inputDigest,
		"approvalPermit":   continuationToken,
	}
	approvedDigest, ok := presentationGroundingDigest(approvedContract)
	if !ok {
		return nil, "", nil, fmt.Errorf("approve tool intent digest unavailable")
	}
	rejectedContract := map[string]any{
		"runId":            runID,
		"toolInvocationId": toolUseID,
		"decision":         "rejected",
		"capability":       toolName,
		"inputDigest":      inputDigest,
		"approvalPermit":   continuationToken,
	}
	rejectedDigest, ok := presentationGroundingDigest(rejectedContract)
	if !ok {
		return nil, "", nil, fmt.Errorf("reject tool intent digest unavailable")
	}
	approved := map[string]any{
		"intentId":      "approve_" + toolUseID,
		"kind":          string(presentationpkg.ActionIntentApproveTool),
		"requestDigest": approvedDigest,
		"jti":           "approve_" + toolUseID,
		"issuedAt":      issuedAt.UTC().Format(time.RFC3339Nano),
		"expiresAt":     expiresAt.UTC().Format(time.RFC3339Nano),
		"approveTool":   approvedContract,
	}
	rejected := map[string]any{
		"intentId":      "reject_" + toolUseID,
		"kind":          string(presentationpkg.ActionIntentApproveTool),
		"requestDigest": rejectedDigest,
		"jti":           "reject_" + toolUseID,
		"issuedAt":      issuedAt.UTC().Format(time.RFC3339Nano),
		"expiresAt":     expiresAt.UTC().Format(time.RFC3339Nano),
		"approveTool":   rejectedContract,
	}
	return map[string]any{
			"title": title,
			"body":  body,
			"details": map[string]any{
				"columns": []any{"项目", "内容"},
				"rows":    rows,
			},
			"approveAction": approved,
			"rejectAction":  rejected,
		}, templateRef, continuationActionPolicy{
			RunID: runID, ToolUseID: toolUseID,
			ContinuationToken: continuationToken,
			Capability:        toolName, InputDigest: inputDigest,
		}, nil
}

type continuationActionPolicy struct {
	RunID             string
	ToolUseID         string
	ContinuationToken string
	Capability        string
	InputDigest       string
}

func (policy continuationActionPolicy) ValidateAction(
	_ context.Context,
	_ string,
	action presentationpkg.ActionIntent,
) error {
	if action.Kind != presentationpkg.ActionIntentApproveTool ||
		action.ApproveTool == nil ||
		action.ApproveTool.RunID != policy.RunID ||
		action.ApproveTool.ToolInvocationID != policy.ToolUseID ||
		action.ApproveTool.Capability != policy.Capability ||
		action.ApproveTool.InputDigest != policy.InputDigest ||
		action.ApproveTool.ApprovalPermit != policy.ContinuationToken {
		return presentationpkg.ErrActionRejected
	}
	if action.ApproveTool.Decision != "approved" &&
		action.ApproveTool.Decision != "rejected" {
		return presentationpkg.ErrActionRejected
	}
	return nil
}

func presentationDocumentMap(document presentationpkg.Document) (map[string]any, error) {
	raw, err := json.Marshal(document)
	if err != nil {
		return nil, err
	}
	var result map[string]any
	if err := json.Unmarshal(raw, &result); err != nil {
		return nil, err
	}
	// Resolver timestamps describe when a semantic document was resolved, not
	// when it became durable. RunRuntime exclusively owns the journal commit
	// timestamp, so the executor must hand off an uncommitted snapshot.
	result["committedAt"] = ""
	return result, nil
}

func stringList(value any) []string {
	switch values := value.(type) {
	case []string:
		return append([]string(nil), values...)
	case []any:
		result := make([]string, 0, len(values))
		for _, value := range values {
			if text, ok := value.(string); ok {
				result = append(result, text)
			}
		}
		return result
	default:
		return nil
	}
}

func anyList(value any) []any {
	switch values := value.(type) {
	case []any:
		return values
	case []map[string]any:
		result := make([]any, 0, len(values))
		for _, item := range values {
			result = append(result, item)
		}
		return result
	default:
		return nil
	}
}

func emptyPresentationValue(value any) bool {
	if value == nil {
		return true
	}
	if text, ok := value.(string); ok {
		return strings.TrimSpace(text) == ""
	}
	return false
}

func presentationValueText(value any) string {
	var text string
	switch typed := value.(type) {
	case string:
		text = strings.TrimSpace(typed)
	case json.Number:
		text = typed.String()
	case int:
		text = fmt.Sprintf("%d", typed)
	case int32:
		text = fmt.Sprintf("%d", typed)
	case int64:
		text = fmt.Sprintf("%d", typed)
	case float64:
		text = fmt.Sprintf("%v", typed)
	case bool:
		text = fmt.Sprintf("%t", typed)
	default:
		return ""
	}
	if len([]rune(text)) > 2000 || strings.ContainsAny(text, "<>\x00") {
		return ""
	}
	return text
}

func presentationSurfaceCapabilities(values map[string]any) presentationpkg.SurfaceCapabilities {
	supported := make(map[generated.AssistantPresentationNodeKind]bool)
	supportedActions := make(map[string]bool)
	appendKind := func(raw any) {
		kind, err := generated.ParseAssistantPresentationNodeKind(
			strings.TrimSpace(stringValue(raw)),
		)
		if err == nil && kind != generated.AssistantPresentationNodeKindUnknown {
			supported[kind] = true
		}
	}
	switch raw := values["supportedNodeKinds"].(type) {
	case []any:
		for _, value := range raw {
			appendKind(value)
		}
	case []string:
		for _, value := range raw {
			appendKind(value)
		}
	}
	appendAction := func(raw any) {
		operation := strings.TrimSpace(stringValue(raw))
		if operation != "" {
			supportedActions[operation] = true
		}
	}
	switch raw := values["supportedActionIntents"].(type) {
	case []any:
		for _, value := range raw {
			appendAction(value)
		}
	case []string:
		for _, value := range raw {
			appendAction(value)
		}
	}
	density := generated.AssistantPresentationDensityStandard
	if raw := strings.TrimSpace(executionString(values, "density")); raw != "" {
		if parsed, err := generated.ParseAssistantPresentationDensity(raw); err == nil {
			density = parsed
		}
	}
	viewport := strings.TrimSpace(executionString(values, "viewportClass"))
	if viewport == "" {
		viewport = "standard"
	}
	return presentationpkg.SurfaceCapabilities{
		SupportedNodeKinds:     supported,
		SupportedActionIntents: supportedActions,
		ViewportClass:          viewport,
		Density:                density,
	}
}

func objectMap(value any) map[string]any {
	switch typed := value.(type) {
	case map[string]any:
		return typed
	default:
		return nil
	}
}
