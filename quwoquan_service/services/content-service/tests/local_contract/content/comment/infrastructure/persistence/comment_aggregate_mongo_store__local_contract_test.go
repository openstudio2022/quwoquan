package persistence_test

import (
	"os"
	"path/filepath"
	"sort"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	"gopkg.in/yaml.v3"
	. "quwoquan_service/services/content-service/internal/content/comment/infrastructure/persistence"

	commentmodel "quwoquan_service/services/content-service/internal/content/comment/domain/model"
	commentports "quwoquan_service/services/content-service/internal/content/comment/domain/ports"
	"quwoquan_service/services/content-service/tests/support"
)

type commentStorageIndexSpec struct {
	Name string `yaml:"name"`
}

type commentStorageCollectionSpec struct {
	Indexes []commentStorageIndexSpec `yaml:"indexes"`
}

type commentStorageSpec struct {
	Collections map[string]commentStorageCollectionSpec `yaml:"collections"`
}

func TestCommentMongoIndexesMatchDedicatedStorageContract(t *testing.T) {
	path := filepath.Join(
		support.ServiceRoot(),
		"contracts",
		"content",
		"comment",
		"storage.yaml",
	)
	raw, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read comment storage contract: %v", err)
	}
	var storage commentStorageSpec
	if err := yaml.Unmarshal(raw, &storage); err != nil {
		t.Fatalf("decode comment storage contract: %v", err)
	}

	assertMongoIndexNames(
		t,
		"comments",
		storage.Collections["comments"].Indexes,
		CommentMongoIndexes(),
	)
	assertMongoIndexNames(
		t,
		"comment_command_receipts",
		storage.Collections["comment_command_receipts"].Indexes,
		CommentReceiptMongoIndexes(),
	)
	assertMongoIndexNames(
		t,
		"comment_author_rate_limit_locks",
		storage.Collections["comment_author_rate_limit_locks"].Indexes,
		CommentRateLockMongoIndexes(),
	)
	assertMongoIndexNames(
		t,
		"comment_outbox",
		storage.Collections["comment_outbox"].Indexes,
		CommentOutboxMongoIndexes(),
	)
	assertMongoIndexNames(
		t,
		"comment_event_log",
		storage.Collections["comment_event_log"].Indexes,
		CommentEventLogMongoIndexes(),
	)
}

func TestCommentMongoIndexesEnforceCASReceiptExpiryAndEventVersions(t *testing.T) {
	version := mongoIndexOptionsByName(t, CommentMongoIndexes(), "idx_comments_version")
	if version.Unique == nil || !*version.Unique {
		t.Fatal("Comment version CAS index must be unique")
	}

	receiptExpiry := mongoIndexOptionsByName(
		t,
		CommentReceiptMongoIndexes(),
		"idx_comment_command_receipts_expire",
	)
	if receiptExpiry.ExpireAfterSeconds == nil || *receiptExpiry.ExpireAfterSeconds != 0 {
		t.Fatal("Comment command receipts must use Mongo TTL expiry from expiresAt")
	}
	rateLockExpiry := mongoIndexOptionsByName(
		t,
		CommentRateLockMongoIndexes(),
		"idx_comment_author_rate_limit_locks_expire",
	)
	if rateLockExpiry.ExpireAfterSeconds == nil || *rateLockExpiry.ExpireAfterSeconds != 0 {
		t.Fatal("Comment author rate-limit locks must use Mongo TTL expiry from expiresAt")
	}

	outboxVersion := mongoIndexOptionsByName(
		t,
		CommentOutboxMongoIndexes(),
		"idx_comment_outbox_aggregate_version",
	)
	if outboxVersion.Unique == nil || !*outboxVersion.Unique {
		t.Fatal("Comment outbox must accept one fact per aggregate version")
	}
	eventLogVersion := mongoIndexOptionsByName(
		t,
		CommentEventLogMongoIndexes(),
		"idx_comment_event_log_aggregate_version",
	)
	if eventLogVersion.Unique == nil || !*eventLogVersion.Unique {
		t.Fatal("Comment event log must accept one audit fact per aggregate version")
	}
}

func TestCommentMongoReaderProjectionIsWhitelisted(t *testing.T) {
	assertProjectionWhitelist(
		t,
		"CommentPage",
		CommentReadProjection(),
		"_id",
		"version",
		"postId",
		"authorId",
		"authorDisplayNameSnapshot",
		"authorAvatarUrlSnapshot",
		"personaContextVersion",
		"content",
		"replyToCommentId",
		"replyToUserId",
		"parentCommentId",
		"attachmentMediaIds",
		"mentions",
		"assistantMentioned",
		"assistantReplySource",
		"assistantCorrectionStatus",
		"status",
		"isPinned",
		"pinnedAt",
		"createdAt",
		"updatedAt",
		"deletedAt",
	)
	assertProjectionWhitelist(
		t,
		"CommentRelation",
		CommentRelationProjection(),
		"_id",
		"postId",
		"authorId",
		"parentCommentId",
		"status",
	)
}

func TestCommentMongoCommitRequiresFactAtCommittedVersion(t *testing.T) {
	now := time.Now().UTC()
	aggregate, err := commentmodel.Create(commentmodel.CreateParams{
		ID:       "comment-mongo-validation",
		PostID:   "post-mongo-validation",
		AuthorID: "persona-mongo-validation",
		Content:  "Mongo outbox validation",
		Now:      now,
	})
	if err != nil {
		t.Fatalf("create Comment aggregate: %v", err)
	}
	commit := commentports.Commit{
		Aggregate:       aggregate,
		ExpectedVersion: 0,
		IdempotencyKey:  "mongo-validation-key",
		CommandName:     "CreateComment",
		CommandDigest:   "mongo-validation-digest",
		OutboxEvents: []commentports.OutboxEvent{{
			EventID:          "mongo-validation-event",
			EventType:        "CommentCreated",
			AggregateID:      aggregate.ID(),
			AggregateVersion: aggregate.Version(),
			Payload:          []byte(`{"commentId":"comment-mongo-validation"}`),
			OccurredAt:       now,
		}},
	}
	if err := ValidateCommentCommit(commit); err != nil {
		t.Fatalf("valid aggregate and outbox fact must commit together: %v", err)
	}

	commit.OutboxEvents = nil
	commit.EventLogRecords = []commentports.EventLogRecord{{
		EventID:          "mongo-validation-audit-event",
		EventType:        "CommentAttachmentsBound",
		AggregateID:      aggregate.ID(),
		AggregateVersion: aggregate.Version(),
		Payload:          []byte(`{"commentId":"comment-mongo-validation"}`),
		OccurredAt:       now,
	}}
	if err := ValidateCommentCommit(commit); err != nil {
		t.Fatalf("valid aggregate and event-log fact must commit together: %v", err)
	}

	commit.EventLogRecords = nil
	if err := ValidateCommentCommit(commit); err == nil {
		t.Fatal("aggregate commit without an outbox or event-log fact must be rejected")
	}
	commit.OutboxEvents = []commentports.OutboxEvent{{
		EventID:          "mongo-validation-event",
		EventType:        "CommentCreated",
		AggregateID:      aggregate.ID(),
		AggregateVersion: aggregate.Version() - 1,
		Payload:          []byte(`{"commentId":"comment-mongo-validation"}`),
		OccurredAt:       now,
	}}
	if err := ValidateCommentCommit(commit); err == nil {
		t.Fatal("outbox fact with another aggregate version must be rejected")
	}
	commit.OutboxEvents[0].AggregateVersion = aggregate.Version()
	commit.EventLogRecords = []commentports.EventLogRecord{{
		EventID:          "mongo-validation-audit-event",
		EventType:        "CommentAttachmentsBound",
		AggregateID:      aggregate.ID(),
		AggregateVersion: aggregate.Version(),
		Payload:          []byte(`{"commentId":"comment-mongo-validation"}`),
		OccurredAt:       now,
	}}
	if err := ValidateCommentCommit(commit); err == nil {
		t.Fatal("one commit must not target outbox and event log simultaneously")
	}
}

func TestCommentMongoDocumentRoundTripsHiddenAt(t *testing.T) {
	now := time.Now().UTC()
	aggregate, err := commentmodel.Create(commentmodel.CreateParams{
		ID:       "comment-mongo-hidden",
		PostID:   "post-mongo-hidden",
		AuthorID: "persona-mongo-hidden",
		Content:  "hidden snapshot",
		Now:      now,
	})
	if err != nil {
		t.Fatal(err)
	}
	if err := aggregate.Hide("operator-mongo-hidden", now.Add(time.Second)); err != nil {
		t.Fatalf("hide Comment aggregate: %v", err)
	}
	document := CommentAggregateDocumentFromSnapshot(aggregate.Snapshot())
	if document.Status != string(commentmodel.StatusHidden) || document.HiddenAt == nil {
		t.Fatalf("hiddenAt was not persisted into Mongo document: %+v", document)
	}
	restored, err := document.Aggregate()
	if err != nil {
		t.Fatalf("restore hidden Comment from Mongo document: %v", err)
	}
	snapshot := restored.Snapshot()
	if snapshot.Status != commentmodel.StatusHidden ||
		snapshot.HiddenAt == nil ||
		!snapshot.HiddenAt.Equal(now.Add(time.Second)) {
		t.Fatalf("hidden Comment Mongo round trip drifted: %+v", snapshot)
	}
}

func assertMongoIndexNames(
	t *testing.T,
	collection string,
	expected []commentStorageIndexSpec,
	actual []mongo.IndexModel,
) {
	t.Helper()
	expectedNames := make([]string, 0, len(expected))
	for _, index := range expected {
		expectedNames = append(expectedNames, index.Name)
	}
	actualNames := make([]string, 0, len(actual))
	for _, index := range actual {
		if index.Options == nil {
			t.Fatalf("%s has unnamed Mongo index", collection)
		}
		resolved := &options.IndexOptions{}
		for _, apply := range index.Options.List() {
			if err := apply(resolved); err != nil {
				t.Fatalf("%s resolves Mongo index options: %v", collection, err)
			}
		}
		if resolved.Name == nil {
			t.Fatalf("%s has unnamed Mongo index", collection)
		}
		actualNames = append(actualNames, *resolved.Name)
	}
	sort.Strings(expectedNames)
	sort.Strings(actualNames)
	if len(expectedNames) != len(actualNames) {
		t.Fatalf("%s index count drift: metadata=%v code=%v", collection, expectedNames, actualNames)
	}
	for index := range expectedNames {
		if expectedNames[index] != actualNames[index] {
			t.Fatalf("%s indexes drift: metadata=%v code=%v", collection, expectedNames, actualNames)
		}
	}
}

func mongoIndexOptionsByName(
	t *testing.T,
	indexes []mongo.IndexModel,
	name string,
) options.IndexOptions {
	t.Helper()
	for _, index := range indexes {
		if index.Options == nil {
			continue
		}
		resolved := options.IndexOptions{}
		for _, apply := range index.Options.List() {
			if err := apply(&resolved); err != nil {
				t.Fatalf("resolve Mongo index %s: %v", name, err)
			}
		}
		if resolved.Name != nil && *resolved.Name == name {
			return resolved
		}
	}
	t.Fatalf("Mongo index %s is missing", name)
	return options.IndexOptions{}
}

func assertProjectionWhitelist(
	t *testing.T,
	reader string,
	projection bson.D,
	allowedFields ...string,
) {
	t.Helper()
	if len(projection) != len(allowedFields) {
		t.Fatalf("%s projection field count = %d, want %d: %+v", reader, len(projection), len(allowedFields), projection)
	}
	allowed := make(map[string]struct{}, len(allowedFields))
	for _, field := range allowedFields {
		allowed[field] = struct{}{}
	}
	for _, field := range projection {
		if _, found := allowed[field.Key]; !found {
			t.Fatalf("%s projection leaks non-reader field %q", reader, field.Key)
		}
		if field.Value != 1 {
			t.Fatalf("%s projection field %q must be included explicitly", reader, field.Key)
		}
	}
}
