package persistence_test

import (
	. "quwoquan_service/services/content-service/internal/content/post/infrastructure/persistence"
	"testing"
	"time"

	postmodel "quwoquan_service/services/content-service/generated/content/post/contract/model"
	postports "quwoquan_service/services/content-service/internal/content/post/domain/ports"
)

func TestValidatePostCommitRejectsOutboxFactOutsideCommittedVersion(t *testing.T) {
	t.Parallel()

	commit := postports.Commit{
		Post:            &postmodel.Post{ID: "post-1"},
		ExpectedVersion: 3,
		IdempotencyKey:  "post-commit-1",
		Events: []postports.OutboxEvent{{
			EventID:          "event-1",
			EventType:        "PostUpdated",
			AggregateType:    "Post",
			AggregateID:      "post-1",
			AggregateVersion: 3,
			OccurredAt:       time.Now().UTC(),
		}},
	}

	if err := ValidatePostCommit(commit); err == nil {
		t.Fatal("ValidatePostCommit() must reject an event at the old aggregate version")
	}
}

func TestValidatePostCommitAcceptsFactAtNextAggregateVersion(t *testing.T) {
	t.Parallel()

	commit := postports.Commit{
		Post:            &postmodel.Post{ID: "post-1"},
		ExpectedVersion: 3,
		IdempotencyKey:  "post-commit-1",
		Events: []postports.OutboxEvent{{
			EventID:          "event-1",
			EventType:        "PostUpdated",
			AggregateType:    "Post",
			AggregateID:      "post-1",
			AggregateVersion: 4,
			OccurredAt:       time.Now().UTC(),
		}},
	}

	if err := ValidatePostCommit(commit); err != nil {
		t.Fatalf("ValidatePostCommit() error = %v", err)
	}
}

func TestPostOutboxCheckpointRoundTripsTransactionalSequence(t *testing.T) {
	t.Parallel()

	checkpoint := PostOutboxCheckpoint(42)
	gotSequence, err := ParsePostOutboxCheckpoint(checkpoint)
	if err != nil {
		t.Fatalf("ParsePostOutboxCheckpoint() error = %v", err)
	}
	if gotSequence != 42 {
		t.Fatalf("sequence = %d, want 42", gotSequence)
	}
}

func TestParsePostOutboxCheckpointRejectsMalformedValue(t *testing.T) {
	t.Parallel()

	if _, err := ParsePostOutboxCheckpoint("not-a-checkpoint"); err == nil {
		t.Fatal("ParsePostOutboxCheckpoint() must reject malformed checkpoint")
	}
}
