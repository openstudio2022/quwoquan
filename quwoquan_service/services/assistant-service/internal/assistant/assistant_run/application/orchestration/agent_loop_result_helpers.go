package orchestration

import (
	"errors"
	"fmt"

	rterr "quwoquan_service/runtime/errors"
	rtfailures "quwoquan_service/runtime/failures"
	assistantgenerated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
)

func modelFailure(stage string, err error) rtfailures.Failure {
	var appError *rterr.AppError
	if errors.As(err, &appError) {
		return rtfailures.FromCurrentAppError(appError)
	}
	return rtfailures.Failure{
		Code:   "ASSISTANT.MIDDLEWARE.model_runtime_failed",
		Origin: rtfailures.OriginRemoteDependency,
		Kind:   rtfailures.KindModel,
		Nature: rtfailures.NatureTransient,
		Location: rtfailures.Location{
			BusinessObject: "assistant_turn",
			FunctionModule: "assistant_agent_loop",
		},
		Context: rtfailures.Context{Attributes: []rtfailures.ContextAttribute{
			{Key: "stage", Value: stage},
			{Key: "reason", Value: err.Error()},
		}},
	}.Normalized()
}

func toolResultReliable(step ReactStepResult) bool {
	result := step.Tool.Completed.Result
	if result == nil {
		return false
	}
	reliable, ok := result["reliable"].(bool)
	if !ok {
		return true
	}
	return reliable
}

func acceptedReferencesForStep(step ReactStepResult) []map[string]any {
	result := step.Tool.Completed.Result
	raw, ok := result["references"]
	if !ok {
		raw, ok = result["citations"]
		if !ok {
			raw, ok = result["reference"]
			if !ok {
				return []map[string]any{}
			}
		}
	}
	references := []map[string]any{}
	appendEntry := func(entry map[string]any) {
		reference, valid := CanonicalToolReference(entry)
		if !valid {
			return
		}
		references = append(references, reference)
	}
	switch items := raw.(type) {
	case map[string]any:
		appendEntry(items)
	case []any:
		for _, item := range items {
			entry, ok := item.(map[string]any)
			if !ok {
				continue
			}
			appendEntry(entry)
			if len(references) >= 5 {
				break
			}
		}
	case []map[string]any:
		for _, entry := range items {
			appendEntry(entry)
			if len(references) >= 5 {
				break
			}
		}
	}
	return references
}

func referenceDestinationKey(reference map[string]any) (string, bool) {
	rawDestination, ok := reference["destination"].(map[string]any)
	if !ok {
		return "", false
	}
	destination, ok := citationDestinationFromMap(rawDestination)
	if !ok {
		return "", false
	}
	switch destination.Kind {
	case string(assistantgenerated.CitationDestinationKindInternal):
		return destination.Kind + ":" + destination.ObjectTypeRef + ":" + destination.ObjectID, true
	case string(assistantgenerated.CitationDestinationKindExternal):
		return destination.Kind + ":" + destination.URL, true
	default:
		return "", false
	}
}

func stringValue(value any) string {
	if value == nil {
		return ""
	}
	text := fmt.Sprint(value)
	if text == "<nil>" {
		return ""
	}
	return text
}
