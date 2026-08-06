// spec_ref: specs/feature-tree/assistant-run-learning/learning-event-feedback-injection/learning-event-ingestion/spec.md#gwt-001
// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/durable-agent-run-orchestration/spec.md#gwt-001
// readiness_case: append-terminal-learning-fact-local
// readiness_case: consume-assistant-run-completed-local
package local_contract

import (
	"context"
	"errors"
	"testing"
	"time"

	learningapplication "quwoquan_service/services/assistant-service/internal/assistant/assistant_learning_fact/application"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_learning_fact/domain/model"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/runruntime"
	rundomain "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain"
)

type memoryLearningFactStore struct {
	facts    map[string]model.Fact
	sequence int64
}

func (store *memoryLearningFactStore) Append(
	_ context.Context,
	fact model.Fact,
) (model.Receipt, error) {
	if store.facts == nil {
		store.facts = map[string]model.Fact{}
	}
	if existing, found := store.facts[fact.StorageID]; found {
		if existing.PayloadDigest != fact.PayloadDigest {
			return model.Receipt{}, learningapplication.ErrIdentityConflict
		}
		return model.Receipt{
			EventID:        existing.EventID,
			Accepted:       true,
			Deduplicated:   true,
			AppendSequence: existing.AppendSequence,
			PayloadDigest:  existing.PayloadDigest,
			RecordedAt:     existing.RecordedAt,
		}, nil
	}
	store.sequence++
	fact.AppendSequence = store.sequence
	store.facts[fact.StorageID] = fact
	return model.Receipt{
		EventID:        fact.EventID,
		Accepted:       true,
		AppendSequence: fact.AppendSequence,
		PayloadDigest:  fact.PayloadDigest,
		RecordedAt:     fact.RecordedAt,
	}, nil
}

type fixedRunOwnerReader struct {
	owner rundomain.Owner
	found bool
	err   error
}

type terminalLifecycleStore struct {
	event        runruntime.TerminalEvent
	acknowledged int
	claimed      bool
}

func (store *terminalLifecycleStore) ClaimPendingTerminalEvents(
	context.Context,
	string,
	time.Time,
	time.Duration,
	int,
) ([]runruntime.TerminalEvent, error) {
	if store.claimed || store.acknowledged != 0 {
		return nil, nil
	}
	store.claimed = true
	return []runruntime.TerminalEvent{store.event}, nil
}

func (store *terminalLifecycleStore) AcknowledgeTerminalEvent(
	context.Context,
	string,
	string,
	time.Time,
) error {
	store.acknowledged++
	return nil
}

func (store *terminalLifecycleStore) ScheduleTerminalEventRetry(
	context.Context,
	string,
	string,
	time.Time,
	time.Time,
	string,
) error {
	return errors.New("unexpected terminal retry")
}

func (store *terminalLifecycleStore) ReleaseTerminalEventClaim(
	context.Context,
	string,
	string,
) error {
	return errors.New("unexpected terminal claim release")
}

func appendUserFact(
	ctx context.Context,
	service *learningapplication.AssistantLearningFactAppender,
	command model.AppendCommand,
	trusted model.TrustedContext,
) (model.Receipt, error) {
	return service.Append(ctx, learningapplication.AppendInput{
		Kind:           learningapplication.AppendKindUserFeedback,
		Command:        command,
		TrustedContext: &trusted,
	})
}

func (reader fixedRunOwnerReader) ResolveRunOwner(
	context.Context,
	string,
) (rundomain.Owner, bool, error) {
	return reader.owner, reader.found, reader.err
}

func TestLearningFactAppendIsDurablyIdempotentAndRejectsConflict(
	t *testing.T,
) {
	t.Parallel()
	now := time.Date(2026, 7, 26, 12, 0, 0, 0, time.UTC)
	store := &memoryLearningFactStore{}
	service := learningapplication.NewAssistantLearningFactAppender(
		store,
		fixedRunOwnerReader{
			owner: rundomain.Owner{
				UserID:    "account-1",
				PersonaID: "persona-1",
			},
			found: true,
		},
		func() time.Time { return now },
	)
	command := model.AppendCommand{
		EventID:          "feedback-1",
		FactType:         model.FactTypeUserFeedback,
		AssistantTurnID:  "turn-1",
		ReferralSource:   "article",
		DomainID:         "assistant",
		FeedbackType:     "thumbs_up",
		FeedbackScore:    1,
		TrainingEligible: false,
		OccurredAt:       now,
	}
	trusted := model.TrustedContext{
		UserID:    "account-1",
		PersonaID: "persona-1",
		TraceID:   "trace-first",
	}
	first, err := appendUserFact(
		t.Context(),
		service,
		command,
		trusted,
	)
	if err != nil {
		t.Fatal(err)
	}
	trusted.TraceID = "trace-retry"
	replayed, err := appendUserFact(
		t.Context(),
		service,
		command,
		trusted,
	)
	if err != nil {
		t.Fatal(err)
	}
	if first.AppendSequence != replayed.AppendSequence ||
		first.PayloadDigest != replayed.PayloadDigest ||
		!replayed.Deduplicated ||
		len(store.facts) != 1 {
		t.Fatalf("first=%+v replayed=%+v facts=%d", first, replayed, len(store.facts))
	}
	stored := store.facts[model.Identity(command.EventID)]
	if stored.AssistantTurnID != "turn-1" ||
		stored.ReferralSource != "article" {
		t.Fatalf("fact provenance=%+v", stored)
	}

	command.FeedbackType = "thumbs_down"
	if _, err := appendUserFact(
		t.Context(),
		service,
		command,
		trusted,
	); !errors.Is(err, learningapplication.ErrIdentityConflict) {
		t.Fatalf("identity conflict error=%v", err)
	}
}

func TestLearningFactFailsClosedForOwnerAndRestrictedTraining(
	t *testing.T,
) {
	t.Parallel()
	service := learningapplication.NewAssistantLearningFactAppender(
		&memoryLearningFactStore{},
		fixedRunOwnerReader{
			owner: rundomain.Owner{
				UserID:    "account-1",
				PersonaID: "persona-1",
			},
			found: true,
		},
		nil,
	)
	command := model.AppendCommand{
		EventID:          "feedback-sensitive",
		FactType:         model.FactTypeUserFeedback,
		AssistantTurnID:  "turn-1",
		ReferralSource:   "article",
		DomainID:         "assistant",
		FeedbackType:     "text",
		FeedbackText:     "raw private feedback",
		TrainingEligible: true,
	}
	if _, err := appendUserFact(
		t.Context(),
		service,
		command,
		model.TrustedContext{
			UserID:    "account-1",
			PersonaID: "persona-forged",
		},
	); !errors.Is(err, learningapplication.ErrOwnerMismatch) {
		t.Fatalf("owner mismatch error=%v", err)
	}
	command.TriggerMessageID = "unbound-message"
	if _, err := appendUserFact(
		t.Context(),
		service,
		command,
		model.TrustedContext{
			UserID:    "account-1",
			PersonaID: "persona-1",
		},
	); !errors.Is(err, learningapplication.ErrInvalid) {
		t.Fatalf("unbound trigger message error=%v", err)
	}
	command.TriggerMessageID = ""
	if _, err := appendUserFact(
		t.Context(),
		service,
		command,
		model.TrustedContext{
			UserID:    "account-1",
			PersonaID: "persona-1",
		},
	); !errors.Is(err, learningapplication.ErrInvalid) {
		t.Fatalf("restricted training error=%v", err)
	}
}

func TestLearningFactSingleIngressFailsClosedAcrossProducerKinds(t *testing.T) {
	t.Parallel()
	store := &memoryLearningFactStore{}
	service := learningapplication.NewAssistantLearningFactAppender(
		store,
		fixedRunOwnerReader{
			owner: rundomain.Owner{UserID: "account-1", PersonaID: "persona-1"},
			found: true,
		},
		nil,
	)
	userCommand := model.AppendCommand{
		EventID: "feedback-typed-ingress", FactType: model.FactTypeUserFeedback,
		AssistantTurnID: "turn-1", ReferralSource: "article", DomainID: "assistant",
		FeedbackType: "thumbs_up", FeedbackScore: 1,
	}
	if _, err := service.Append(t.Context(), learningapplication.AppendInput{
		Kind: learningapplication.AppendKindUserFeedback, Command: userCommand,
	}); !errors.Is(err, learningapplication.ErrUnauthorized) {
		t.Fatalf("missing trusted context error=%v", err)
	}

	trusted := model.TrustedContext{UserID: "account-1", PersonaID: "persona-1"}
	serviceCommand := model.AppendCommand{
		EventID: "scorecard-typed-ingress", FactType: model.FactTypeServiceScorecard,
		AssistantTurnID: "turn-1", ReferralSource: "service", DomainID: "assistant",
		MetricID: "turn_completion", MetricValue: 1, MetricSource: "service_auto",
	}
	if _, err := service.Append(t.Context(), learningapplication.AppendInput{
		Kind: learningapplication.AppendKindTerminalScorecard, Command: serviceCommand,
		TrustedContext: &trusted,
	}); !errors.Is(err, learningapplication.ErrUnauthorized) {
		t.Fatalf("caller-supplied terminal identity error=%v", err)
	}
	if _, err := service.Append(t.Context(), learningapplication.AppendInput{
		Kind: learningapplication.AppendKindTerminalScorecard, Command: userCommand,
	}); !errors.Is(err, learningapplication.ErrInvalid) {
		t.Fatalf("terminal user fact error=%v", err)
	}
	if _, err := service.Append(t.Context(), learningapplication.AppendInput{
		Kind: learningapplication.AppendKindTerminalScorecard, Command: serviceCommand,
	}); err != nil {
		t.Fatalf("valid terminal scorecard: %v", err)
	}
}

func TestTerminalRunConsumerAppendsAndDeduplicatesCanonicalScorecard(t *testing.T) {
	t.Parallel()
	now := time.Date(2026, 8, 6, 0, 0, 0, 0, time.UTC)
	store := &memoryLearningFactStore{}
	service := learningapplication.NewAssistantLearningFactAppender(
		store,
		fixedRunOwnerReader{
			owner: rundomain.Owner{UserID: "account-terminal", PersonaID: "persona-terminal"},
			found: true,
		},
		func() time.Time { return now },
	)
	source := &terminalLifecycleStore{event: runruntime.TerminalEvent{
		EventID: "run-terminal:completed", RunID: "run-terminal", DomainID: "travel",
		Outcome: "completed", OccurredAt: now,
	}}
	relay := runruntime.NewTerminalRunRelay(
		source,
		runruntime.TerminalEventPublisherFunc(func(context.Context, runruntime.TerminalEvent) error {
			return nil
		}),
		[]runruntime.TerminalEventHandler{runruntime.TerminalEventHandlerFunc(func(
			ctx context.Context,
			event runruntime.TerminalEvent,
		) error {
			_, err := service.AppendTerminalRun(ctx, learningapplication.TerminalRunEvent{
				RunID: event.RunID, DomainID: event.DomainID, Outcome: event.Outcome,
				OccurredAt: event.OccurredAt,
			})
			return err
		})},
		"learning-fact-local-consumer",
		time.Second,
		1,
	)
	processed, err := relay.FlushOnce(t.Context())
	if err != nil || processed != 1 || source.acknowledged != 1 || len(store.facts) != 1 {
		t.Fatalf("first relay=(%d,%v) acknowledged=%d facts=%d",
			processed, err, source.acknowledged, len(store.facts))
	}
	processed, err = relay.FlushOnce(t.Context())
	if err != nil || processed != 0 || source.acknowledged != 1 || len(store.facts) != 1 {
		t.Fatalf("replayed relay=(%d,%v) acknowledged=%d facts=%d",
			processed, err, source.acknowledged, len(store.facts))
	}
	fact := store.facts[model.Identity("turn:run-terminal:completion")]
	if fact.UserID != "account-terminal" || fact.PersonaID != "persona-terminal" ||
		fact.FactType != model.FactTypeServiceScorecard ||
		fact.MetricID != "turn_completion" || fact.MetricValue != 1 ||
		fact.MetricSource != "service_auto" || fact.TrainingEligible {
		t.Fatalf("terminal learning fact=%+v", fact)
	}
}
