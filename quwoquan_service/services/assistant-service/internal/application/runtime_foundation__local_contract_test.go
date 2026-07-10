package application

import (
	"encoding/json"
	"testing"
	"time"

	rtclock "quwoquan_service/runtime/clock"
	rtfailures "quwoquan_service/runtime/failures"
	rtid "quwoquan_service/runtime/id"
	"quwoquan_service/runtime/streaming"
)

func TestRuntimeFoundationSmoke(t *testing.T) {
	fakeClock := rtclock.NewFake(time.Date(2026, 4, 29, 2, 0, 0, 0, time.UTC))
	generator := rtid.MustNewGenerator(
		rtid.PrefixAssistantTurn,
		rtid.WithClock(fakeClock.Now),
	)
	turnID, err := generator.Generate()
	if err != nil {
		t.Fatalf("Generate() error = %v", err)
	}
	if !rtid.IsValid(turnID) {
		t.Fatalf("generated id is invalid: %s", turnID)
	}

	failure := rtfailures.Failure{
		Code:   "ASSISTANT.MIDDLEWARE.llm_timeout",
		Origin: rtfailures.OriginRemoteDependency,
		Kind:   rtfailures.KindTimeout,
		Nature: rtfailures.NatureTransient,
	}
	decision := rtfailures.DefaultRecoveryPolicy{}.Decide(
		failure,
		rtfailures.EntryContext{Kind: "assistant_turn", EntryID: turnID},
		rtfailures.BoundaryContext{Boundary: "model_provider", RemainingBudget: 1},
	)
	if decision.Action != rtfailures.RecoveryActionRetry {
		t.Fatalf("recovery action = %s", decision.Action)
	}

	envelope, err := streaming.NewEnvelope("assistant.turn.started", 1, map[string]string{"turnId": turnID})
	if err != nil {
		t.Fatalf("NewEnvelope() error = %v", err)
	}
	envelope.ResumeToken = streaming.NewResumeToken(turnID, envelope.Seq)
	transport := streaming.NewFakeTransport()
	transport.Publish(turnID, roundTripEnvelope(t, envelope))
	events := transport.List(turnID, 0)
	if len(events) != 1 || events[0].Seq != 1 {
		t.Fatalf("published events = %#v", events)
	}
}

func roundTripEnvelope(t *testing.T, envelope streaming.Envelope) streaming.Envelope {
	t.Helper()
	payload, err := json.Marshal(envelope)
	if err != nil {
		t.Fatalf("marshal envelope: %v", err)
	}
	var decoded streaming.Envelope
	if err := json.Unmarshal(payload, &decoded); err != nil {
		t.Fatalf("unmarshal envelope: %v", err)
	}
	return decoded
}
