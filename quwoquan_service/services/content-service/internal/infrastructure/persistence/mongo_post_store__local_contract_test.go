package persistence

import (
	"testing"
	"time"

	postmodel "quwoquan_service/services/content-service/internal/domain/post/model"
	postports "quwoquan_service/services/content-service/internal/domain/post/ports"
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

	if err := validatePostCommit(commit); err == nil {
		t.Fatal("validatePostCommit() must reject an event at the old aggregate version")
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

	if err := validatePostCommit(commit); err != nil {
		t.Fatalf("validatePostCommit() error = %v", err)
	}
}

func TestPostOutboxCheckpointRoundTripsTransactionalSequence(t *testing.T) {
	t.Parallel()

	checkpoint := postOutboxCheckpoint(42)
	gotSequence, err := parsePostOutboxCheckpoint(checkpoint)
	if err != nil {
		t.Fatalf("parsePostOutboxCheckpoint() error = %v", err)
	}
	if gotSequence != 42 {
		t.Fatalf("sequence = %d, want 42", gotSequence)
	}
}

func TestParsePostOutboxCheckpointRejectsMalformedValue(t *testing.T) {
	t.Parallel()

	if _, err := parsePostOutboxCheckpoint("not-a-checkpoint"); err == nil {
		t.Fatal("parsePostOutboxCheckpoint() must reject malformed checkpoint")
	}
}
