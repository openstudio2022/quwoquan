package post_test

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"quwoquan_service/runtime/commandmeta"
	"quwoquan_service/services/content-service/internal/content/post/infrastructure/testsupport"
	"testing"
	"time"
)

// spec_ref: specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/canonical-search-contract/spec.md#req-006
func TestPostLifecycleVisitedAtWireIsNullOrTimestamp(t *testing.T) {
	for _, visited := range []time.Time{{}, time.Date(2026, 4, 5, 6, 30, 0, 0, time.UTC)} {
		store := testsupport.NewPostStore(nil)
		svc := newVisitedAtService(store)
		_, err := svc.SubmitPostPublication(commandmeta.WithIdempotencyKey(context.Background(), "intent-visited-wire"), visitedAtPublicationCommand("wire", visited))
		if err != nil {
			t.Fatal(err)
		}
		events := store.OutboxEvents()
		if len(events) != 1 {
			t.Fatal(len(events))
		}
		var payload map[string]any
		if err = json.Unmarshal(events[0].Payload, &payload); err != nil {
			t.Fatal(err)
		}
		if python := os.Getenv("QWQ_POST_WIRE_PYTHON"); python != "" {
			root, _ := filepath.Abs(filepath.Join("..", "..", "..", "..", "..", "..", ".."))
			script := `import json,sys
sys.path.insert(0,sys.argv[1]+"/services/recommendation-service")
from internal.recommendation.recommendation_candidate_index_view.adapters.inbound.stream.post_lifecycle_consumer import decode_post_lifecycle as candidate
from internal.recommendation.recommendation_feature_profile_view.adapters.inbound.stream.post_lifecycle_consumer import decode_post_lifecycle as feature
wire=dict(eventId="actual",eventType="PostPublished",aggregateType="Post",aggregateId=sys.argv[2],aggregateVersion=sys.argv[3],occurredAt="2026-09-13T00:00:00Z",payload=sys.argv[4])
assert candidate(wire) is not None and feature(wire) is not None
print("ACTUAL_POST_PUBLICATION_TWO_PRODUCTION_DECODERS_PASS")`
			cmd := exec.Command(python, "-B", "-c", script, root, events[0].AggregateID, fmt.Sprint(events[0].AggregateVersion), string(events[0].Payload))
			cmd.Env = append(os.Environ(), "PYTHONDONTWRITEBYTECODE=1")
			if output, err := cmd.CombinedOutput(); err != nil {
				t.Fatalf("producer/decoder mismatch %v %s", err, output)
			} else {
				t.Log(string(output))
			}
		}
		value, present := payload["visitedAt"]
		if !present {
			t.Fatal("nullable visitedAt absent")
		}
		if visited.IsZero() {
			if value != nil {
				t.Fatalf("absent visitedAt must be null: %#v", value)
			}
		} else if value != visited.Format(time.RFC3339) {
			t.Fatal(value)
		}
		if payload["sourceVersion"] != float64(events[0].AggregateVersion) {
			t.Fatal("sourceVersion must match same commit envelope", payload["sourceVersion"], events[0].AggregateVersion)
		}
		// 普通业务来源必须显式null，不能推断缺失来源。
		for _, key := range []string{"environment", "sourceOwner", "releaseId", "manifestDigest", "releaseDigest"} {
			if _, ok := payload[key]; !ok {
				t.Fatalf("explicit source missing %s", key)
			}
			if payload[key] != nil {
				t.Fatalf("ordinary producer forged %s", key)
			}
		}
	}
}
