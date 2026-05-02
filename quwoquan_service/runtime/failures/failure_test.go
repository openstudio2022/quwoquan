package failures

import (
	"encoding/json"
	"testing"

	runtimeerrors "quwoquan_service/runtime/errors"
)

func TestFailureResponseCodec(t *testing.T) {
	failure := Failure{
		Code:   "ASSISTANT.MIDDLEWARE.llm_timeout",
		Origin: OriginRemoteDependency,
		Kind:   KindTimeout,
		Nature: NatureTransient,
		Location: Location{
			BusinessObject: "assistant_turn",
			FunctionModule: "llm_client",
		},
		Context: Context{
			Attributes: []ContextAttribute{
				{Key: "downstreamStatus", Value: "504"},
			},
		},
	}
	response := ToResponse(failure, ResponseOptions{
		RequestID: "request-1",
		TraceID:   "trace-1",
	})

	payload, err := json.Marshal(response)
	if err != nil {
		t.Fatalf("marshal response: %v", err)
	}
	var decoded ErrorResponse
	if err := json.Unmarshal(payload, &decoded); err != nil {
		t.Fatalf("unmarshal response: %v", err)
	}
	if decoded.Context.Attributes[0].Value != "504" {
		t.Fatalf("context value should stay string, got %q", decoded.Context.Attributes[0].Value)
	}
	if decoded.Code != failure.Code {
		t.Fatalf("unexpected code: %s", decoded.Code)
	}
}

func TestCurrentAppErrorMapping(t *testing.T) {
	current := runtimeerrors.NewUnavailable(
		runtimeerrors.ModuleAssistant,
		"",
		"llm timeout",
	)
	failure := FromCurrentAppError(current)

	if failure.Origin != OriginRemoteDependency {
		t.Fatalf("unexpected origin: %s", failure.Origin)
	}
	if failure.Kind != KindUnavailable {
		t.Fatalf("unexpected kind: %s", failure.Kind)
	}
	if failure.Context.Attributes[0].Value != "ASSISTANT" {
		t.Fatalf("unexpected module context: %s", failure.Context.Attributes[0].Value)
	}
}

func TestUnknownFallback(t *testing.T) {
	failure := Failure{}.Normalized()

	if failure.Code != UnknownCode {
		t.Fatalf("unexpected unknown code: %s", failure.Code)
	}
	if failure.Location.BusinessObject != "unknown" {
		t.Fatalf("unexpected location: %s", failure.Location.BusinessObject)
	}
}
