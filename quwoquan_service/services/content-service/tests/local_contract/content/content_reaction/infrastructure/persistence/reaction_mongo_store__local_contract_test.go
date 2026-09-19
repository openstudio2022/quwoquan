package persistence_test

import (
	"gopkg.in/yaml.v3"
	"os"
	"path/filepath"
	. "quwoquan_service/services/content-service/internal/content/content_reaction/infrastructure/persistence"
	"reflect"
	"runtime"
	"strings"
	"testing"
	"time"

	reactionapp "quwoquan_service/services/content-service/internal/content/content_reaction/application/reaction"
	reactiondomain "quwoquan_service/services/content-service/internal/content/content_reaction/domain/reaction"
	reactionports "quwoquan_service/services/content-service/internal/content/content_reaction/domain/reaction/ports"
)

func TestReactionMongoDocumentRoundTripPreservesRelationIdentity(t *testing.T) {
	t.Parallel()

	actor, err := reactiondomain.NewActor(reactiondomain.ActorDimensionDevice, "device-1")
	if err != nil {
		t.Fatalf("actor: %v", err)
	}
	identity, err := reactiondomain.NewPostIdentity("post-1", actor)
	if err != nil {
		t.Fatalf("identity: %v", err)
	}
	aggregate, err := reactiondomain.New(identity, reactiondomain.ValueLike, time.Now().UTC())
	if err != nil {
		t.Fatalf("aggregate: %v", err)
	}
	restored, err := ReactionFromDocument(ReactionDocumentFromSnapshot(aggregate.Snapshot()))
	if err != nil {
		t.Fatalf("round trip: %v", err)
	}
	if restored.ID() != aggregate.ID() ||
		restored.Version() != aggregate.Version() ||
		!restored.IsLiked() ||
		restored.Identity() != identity {
		t.Fatalf("reaction mapper changed aggregate: %+v", restored.Snapshot())
	}
}

func TestReactionMongoCommitRejectsWrongOutboxVersion(t *testing.T) {
	t.Parallel()

	actor, _ := reactiondomain.NewActor(reactiondomain.ActorDimensionPersona, "persona-1")
	identity, _ := reactiondomain.NewPostIdentity("post-1", actor)
	aggregate, err := reactiondomain.New(identity, reactiondomain.ValueLike, time.Now().UTC())
	if err != nil {
		t.Fatalf("aggregate: %v", err)
	}
	err = ValidateReactionCommit(reactionports.Commit{
		Aggregate:       aggregate,
		ExpectedVersion: 0,
		IdempotencyKey:  "reaction-commit",
		CommandName:     "LikePost",
		CommandDigest:   "digest",
		Changed:         true,
		Events: []reactionports.OutboxFact{{
			EventID:          "event-1",
			EventType:        reactionapp.EventTypeContentReactionSet,
			AggregateID:      aggregate.ID(),
			AggregateVersion: aggregate.Version() + 1,
			Payload:          []byte(`{}`),
			OccurredAt:       time.Now().UTC(),
		}},
	})
	if err == nil || !strings.Contains(err.Error(), "version_conflict") {
		t.Fatalf("mismatched outbox version must fail, got %v", err)
	}
}

// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/reaction-state-counter/spec.md#gwt-003
// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/reaction-state-counter/spec.md#gwt-006
// 本测试仅锁定声明结构；状态分支执行、数字收敛和事务仲裁由后续真实测试证明。
func TestReactionProtocolContractSeparatesStatisticsAttachmentAndReceipt(t *testing.T) {
	_, file, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("resolve contract source")
	}
	serviceRoot := filepath.Clean(filepath.Join(filepath.Dir(file), "../../../../../.."))
	raw, err := os.ReadFile(filepath.Join(serviceRoot, "contracts/content/content_reaction/fields.yaml"))
	if err != nil {
		t.Fatal(err)
	}
	var document struct {
		Enums map[string]struct {
			Values []string `yaml:"values"`
		} `yaml:"enums"`
		Types map[string]struct {
			Fields []struct {
				Name        string   `yaml:"name"`
				Type        string   `yaml:"type"`
				Constraints []string `yaml:"constraints"`
				LogPolicy   string   `yaml:"log_policy"`
				MaxBytes    int      `yaml:"max_utf8_bytes"`
			} `yaml:"fields"`
		} `yaml:"types"`
	}
	if err := yaml.Unmarshal(raw, &document); err != nil {
		t.Fatal(err)
	}
	for name, want := range map[string][]string{
		"ContentReactionStatisticsState": {"available", "stale", "unavailable"},
		"ContentReactionAttachmentState": {"attached", "not_applicable", "unavailable"},
		"ContentReactionReceiptOutcome":  {"committed", "rejected", "expired", "history_unavailable"},
	} {
		if got := document.Enums[name].Values; !reflect.DeepEqual(got, want) {
			t.Fatalf("%s merges distinct result states: %v", name, got)
		}
	}
	for _, name := range []string{"targetKind", "targetId", "actorDimension", "actorId", "audience", "allowedReactions", "expectedVersion", "issuedAt", "acceptUntil"} {
		found := false
		for _, field := range document.Types["ContentReactionMutationBasisClaims"].Fields {
			if field.Name == name {
				found = true
			}
		}
		if !found {
			t.Fatalf("missing actor-bound reaction basis claim %s", name)
		}
	}
	counts := 0
	for _, field := range document.Types["ContentReactionStatisticsSnapshot"].Fields {
		if field.Name == "likeCount" || field.Name == "dislikeCount" {
			counts++
			if field.Type != "int64" || !reflect.DeepEqual(field.Constraints, []string{"NOT_NULL", "MIN_0"}) {
				t.Fatalf("available statistics require nonnegative facts: %+v", field)
			}
		}
		if field.Name == "actorId" || field.Name == "reaction" || field.Name == "pending" {
			t.Fatal("public statistics must not contain private actor state or local intent")
		}
	}
	if counts != 2 {
		t.Fatal("statistics snapshot must declare both target reaction counts")
	}
	basisFound := false
	for _, field := range document.Types["ContentReactionMutationEvidence"].Fields {
		if field.Name == "mutationBasis" {
			basisFound = true
			if field.MaxBytes != 4096 || field.LogPolicy != "drop" {
				t.Fatal("mutation basis must be bounded and excluded from logs")
			}
		}
	}
	if !basisFound {
		t.Fatal("mutation evidence must retain the signed basis")
	}
	for _, field := range document.Types["ContentReactionCommandRecoverySlice"].Fields {
		if field.Name == "likeCount" || field.Name == "liked" || field.Name == "reaction" {
			t.Fatal("current reaction or count cannot prove a historical command result")
		}
	}
}
