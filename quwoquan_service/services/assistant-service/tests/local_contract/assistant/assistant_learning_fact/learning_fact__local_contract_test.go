// spec_ref: specs/feature-tree/assistant-run-learning/learning-event-feedback-injection/learning-event-ingestion/spec.md#gwt-001
package local_contract

import (
	"context"
	"errors"
	"testing"
	"time"

	learningapplication "quwoquan_service/services/assistant-service/internal/assistant/assistant_learning_fact/application"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_learning_fact/domain/model"
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
	service := learningapplication.NewService(
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
	first, err := service.AppendUserFact(
		t.Context(),
		command,
		trusted,
	)
	if err != nil {
		t.Fatal(err)
	}
	trusted.TraceID = "trace-retry"
	replayed, err := service.AppendUserFact(
		t.Context(),
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
	if _, err := service.AppendUserFact(
		t.Context(),
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
	service := learningapplication.NewService(
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
	if _, err := service.AppendUserFact(
		t.Context(),
		command,
		model.TrustedContext{
			UserID:    "account-1",
			PersonaID: "persona-forged",
		},
	); !errors.Is(err, learningapplication.ErrOwnerMismatch) {
		t.Fatalf("owner mismatch error=%v", err)
	}
	command.TriggerMessageID = "unbound-message"
	if _, err := service.AppendUserFact(
		t.Context(),
		command,
		model.TrustedContext{
			UserID:    "account-1",
			PersonaID: "persona-1",
		},
	); !errors.Is(err, learningapplication.ErrInvalid) {
		t.Fatalf("unbound trigger message error=%v", err)
	}
	command.TriggerMessageID = ""
	if _, err := service.AppendUserFact(
		t.Context(),
		command,
		model.TrustedContext{
			UserID:    "account-1",
			PersonaID: "persona-1",
		},
	); !errors.Is(err, learningapplication.ErrInvalid) {
		t.Fatalf("restricted training error=%v", err)
	}
}
