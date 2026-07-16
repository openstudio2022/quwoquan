package circlebehaviorfact

import (
	"context"
	"testing"

	"quwoquan_service/runtime/operation"
	behaviorfactmodel "quwoquan_service/services/circle-service/internal/domain/circle/circle_behavior_fact/model"
	behaviorfactports "quwoquan_service/services/circle-service/internal/domain/circle/circle_behavior_fact/ports"
)

type factSinkSpy struct {
	request behaviorfactports.AppendRequest
}

func (sink *factSinkSpy) Append(_ context.Context, request behaviorfactports.AppendRequest) (behaviorfactports.AppendReceipt, error) {
	sink.request = request
	return behaviorfactports.AppendReceipt{FactID: request.Fact.ID}, nil
}

type activeCircleReader struct{}

func (activeCircleReader) ReadCircleState(context.Context, string) (string, bool, error) {
	return "active", true, nil
}

func TestWriterDerivesActorAndAttributionOnlyFromOperationContext(t *testing.T) {
	sink := &factSinkSpy{}
	writer := NewWriter(sink, activeCircleReader{})
	ctx := operation.WithContext(context.Background(), operation.Context{
		OperationID: "circle.circle_behavior_fact.ReportCircleBehavior",
		RequestID:   "request-1", TraceID: "trace-1", IdempotencyKey: "key-1", SessionID: "session-1",
		Actor: operation.ActorContext{AccountID: "account-1", PersonaID: "persona-1", DeviceActorID: "ignored-device"},
	})
	result, err := writer.Append(ctx, AppendCommand{CircleID: "circle-1", EventType: behaviorfactmodel.BehaviorEventTypeImpression})
	if err != nil {
		t.Fatal(err)
	}
	if result.FactID == "" || sink.request.CommandDigest == "" {
		t.Fatalf("append identity missing: result=%#v request=%#v", result, sink.request)
	}
	fact := sink.request.Fact
	if fact.ActorKind != "persona" || fact.PersonaID != "persona-1" || fact.DeviceActorID != "" ||
		fact.SessionID != "session-1" || fact.RequestID != "request-1" {
		t.Fatalf("trusted attribution drift: %#v", fact)
	}
}

func TestWriterRejectsMissingTrustedContextAndUnknownEventType(t *testing.T) {
	writer := NewWriter(&factSinkSpy{}, activeCircleReader{})
	if _, err := writer.Append(context.Background(), AppendCommand{CircleID: "circle-1", EventType: behaviorfactmodel.BehaviorEventTypeImpression}); err == nil {
		t.Fatal("missing trusted Operation Context must fail")
	}
	ctx := operation.WithContext(context.Background(), operation.Context{
		OperationID: "circle.circle_behavior_fact.ReportCircleBehavior",
		RequestID:   "request-1", TraceID: "trace-1", IdempotencyKey: "key-1", SessionID: "session-1",
		Actor: operation.ActorContext{DeviceActorID: "device-1"},
	})
	if _, err := writer.Append(ctx, AppendCommand{CircleID: "circle-1", EventType: "invented"}); err == nil {
		t.Fatal("unregistered eventType must fail")
	}
}
