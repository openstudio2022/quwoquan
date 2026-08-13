// spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-001
// spec_ref: specs/feature-tree/discovery-content/spec.md#dom-005.t1
// spec_ref: specs/feature-tree/discovery-content/spec.md#dom-005.t3
// spec_ref: specs/feature-tree/discovery-content/spec.md#dom-005.t4
package releaseimport_test

import (
	"context"
	"crypto/sha256"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"slices"
	"sort"
	"strings"
	"testing"
	"time"

	postports "quwoquan_service/services/content-service/internal/content/post/domain/ports"
	releaseimport "quwoquan_service/services/content-service/internal/content/post/infrastructure/releaseimport"
)

func TestReplayRepairOptionsAreExplicitAndCountBound(t *testing.T) {
	for _, tc := range []struct {
		name          string
		requireReplay bool
		expected      int
		wantError     bool
	}{
		{name: "ordinary import", expected: -1},
		{name: "repair", requireReplay: true, expected: 4},
		{name: "idempotent repair", requireReplay: true, expected: 0},
		{name: "replay without count", requireReplay: true, expected: -1, wantError: true},
		{name: "count without replay", expected: 4, wantError: true},
	} {
		t.Run(tc.name, func(t *testing.T) {
			err := releaseimport.ValidateReplayRepairOptions(tc.requireReplay, tc.expected)
			if (err != nil) != tc.wantError {
				t.Fatalf("error=%v wantError=%t", err, tc.wantError)
			}
		})
	}
	for _, tc := range []struct {
		name          string
		requireReplay bool
		path          string
		wantError     bool
	}{
		{name: "ordinary import"},
		{name: "repair source report", requireReplay: true, path: "/repair/source-import.json"},
		{name: "repair missing report", requireReplay: true, wantError: true},
		{name: "report outside repair", path: "/repair/source-import.json", wantError: true},
	} {
		t.Run(tc.name, func(t *testing.T) {
			err := releaseimport.ValidateReplaySourceImportReportOption(tc.requireReplay, tc.path)
			if (err != nil) != tc.wantError {
				t.Fatalf("error=%v wantError=%t", err, tc.wantError)
			}
		})
	}
}

func TestReplayRepairRequiresActiveBindingAndExactTransactionalCount(t *testing.T) {
	want := 4
	opts := releaseimport.ImportOptions{
		ReleaseID:                 "release-a",
		ManifestDigest:            "sha256:" + strings.Repeat("a", 64),
		RequireReplay:             true,
		ExpectedOutboxRepairCount: &want,
	}
	if err := releaseimport.ValidateReplayRepairBinding(opts, false); err == nil {
		t.Fatal("non-active release reached repair transaction")
	}
	if err := releaseimport.ValidateReplayRepairBinding(opts, true); err != nil {
		t.Fatalf("active replay binding rejected: %v", err)
	}
	if err := releaseimport.ValidateExpectedOutboxRepairCount(
		opts,
		releaseimport.ImportedReleaseApplyResult{OutboxEventsRepaired: 3},
	); err == nil {
		t.Fatal("stale repair count was acknowledged")
	}
	if err := releaseimport.ValidateExpectedOutboxRepairCount(
		opts,
		releaseimport.ImportedReleaseApplyResult{OutboxEventsRepaired: 4},
	); err != nil {
		t.Fatalf("exact repair count rejected: %v", err)
	}
}

func TestReplayRepairUsesSourceImportPostBindingsWithoutMigratingIdentity(
	t *testing.T,
) {
	t.Parallel()
	post := releaseimport.PostDoc{
		PostRef:         "posts/article/体验/旧发布身份/1",
		ContentID:       "qwq_data_data_post_legacy_001",
		ContentVersion:  1,
		ContentType:     "article",
		ContentIdentity: "work",
		AuthorID:        "builtin_travel_blogger",
		Admission: releaseimport.ContentAdmission{
			ProcessResult: "completed",
			QualityResult: "passed",
			UsageScope:    "research",
		},
	}
	postRefDerivedID := releaseimport.RuntimePostIDFromPostRef(post.PostRef)
	bindings := []releaseimport.ImportedPostBinding{{
		PostRef: "article/体验/旧发布身份/1", PostID: postRefDerivedID,
		ContentID: post.ContentID, ContentVersion: 1, UsageScope: "research",
		ContentType: "article", AuthorID: post.AuthorID,
	}}
	if err := releaseimport.ValidateImportedPostReplayBindings(
		[]releaseimport.PostDoc{post}, bindings,
	); err != nil {
		t.Fatalf("legacy source-import binding rejected: %v", err)
	}
	if bindings[0].PostID == releaseimport.RuntimePostID(post.ContentID, post.PostRef) {
		t.Fatal("test precondition: legacy and current runtime identities must differ")
	}

	drifted := append([]releaseimport.ImportedPostBinding(nil), bindings...)
	drifted[0].ContentVersion++
	if err := releaseimport.ValidateImportedPostReplayBindings(
		[]releaseimport.PostDoc{post}, drifted,
	); err == nil || !strings.Contains(err.Error(), "GATE_BLOCK") {
		t.Fatalf("drifted source-import binding was accepted: %v", err)
	}

	events, err := releaseimport.BuildImportedPostDeletionLifecycleEvents(
		fourDeletionSnapshots(),
		releaseimport.ImportOptions{
			ReleaseID: "legacy-release", ManifestDigest: "sha256:" + strings.Repeat("a", 64),
			SourceOwner: "qwq_data", ProjectionVersion: 42,
		},
		time.Date(2026, 8, 11, 3, 10, 0, 0, time.UTC),
	)
	if err != nil || len(events) != 4 {
		t.Fatalf("deletion-only replay events=%d err=%v, want 4", len(events), err)
	}
	for _, event := range events {
		if event.EventType != "PostDeleted" {
			t.Fatalf("repair rail emitted non-deletion event: %#v", event)
		}
	}
	if err := releaseimport.ValidateImportedReleaseApplyResult(
		releaseimport.ImportedReleaseApplyResult{
			PostsUpserted: 46, PostDeletionEventsReady: 4,
			OutboxEventsReady: 4, OutboxEventsRepaired: 4,
			Replayed: true, RepairReplay: true,
		},
		46,
	); err != nil {
		t.Fatalf("deletion-only replay result rejected: %v", err)
	}
}

func TestReplaySourceImportReportIsStrictAndCountBound(t *testing.T) {
	t.Parallel()
	post := releaseimport.PostDoc{
		PostRef: "posts/video/体验/legacy-video/1", ContentID: "legacy-video-content",
		ContentVersion: 2, ContentType: "video", ContentIdentity: "work",
		AuthorID: "builtin_video_author",
		Admission: releaseimport.ContentAdmission{
			ProcessResult: "completed", QualityResult: "passed", UsageScope: "research",
		},
	}
	binding := releaseimport.ImportedPostBinding{
		PostRef:   "video/体验/legacy-video/1",
		PostID:    releaseimport.RuntimePostIDFromPostRef(post.PostRef),
		ContentID: post.ContentID, ContentVersion: 2, UsageScope: "research",
		ContentType: "video", AuthorID: post.AuthorID,
	}
	digest := "sha256:" + strings.Repeat("a", 64)
	report := map[string]any{
		"schema": "quwoquan.content_import_report", "status": "imported",
		"environment": "alpha", "releaseId": "legacy-release",
		"sourceOwner": "qwq_data", "manifestDigest": digest,
		"mode": "sync", "deletePolicy": "tombstone",
		"counts": map[string]int{
			"postsLoaded": 1, "postsUpserted": 1, "postsRemoved": 4,
			"outboxEventsAppended": 5,
		},
		"postBindings": []releaseimport.ImportedPostBinding{binding},
		"auditEvents":  []string{"DataReleasePrepared", "DataReleaseActivated"},
	}
	write := func(name string, value map[string]any) string {
		t.Helper()
		raw, err := json.Marshal(value)
		if err != nil {
			t.Fatal(err)
		}
		path := t.TempDir() + "/" + name
		if err := os.WriteFile(path, raw, 0o600); err != nil {
			t.Fatal(err)
		}
		return path
	}
	bindings, err := releaseimport.LoadImportedPostReplayBindings(
		write("import.json", report), "alpha", "legacy-release", digest, "qwq_data",
		[]releaseimport.PostDoc{post},
	)
	if err != nil || len(bindings) != 1 || bindings[0].PostID != binding.PostID {
		t.Fatalf("valid source report bindings=%+v err=%v", bindings, err)
	}

	report["unexpectedSecondTruth"] = true
	if _, err := releaseimport.LoadImportedPostReplayBindings(
		write("unknown.json", report), "alpha", "legacy-release", digest, "qwq_data",
		[]releaseimport.PostDoc{post},
	); err == nil || !strings.Contains(err.Error(), "GATE_BLOCK") {
		t.Fatalf("unknown source report field accepted: %v", err)
	}
}

func TestBuildImportedPostLifecycleEventsUsesOneDurablePostFactStream(t *testing.T) {
	now := time.Date(2026, 8, 1, 2, 49, 50, 0, time.UTC)
	post := releaseimport.PostDoc{
		PostRef:        "video/体验/候选投影/1",
		ContentID:      "travel_video_candidate",
		ContentVersion: 2,
		PoolSourceType: "data",
		VariantPurpose: "original",
		PoolStatus:     "active",
		Admission: releaseimport.ContentAdmission{
			ProcessResult: "completed",
			QualityResult: "passed",
			UsageScope:    "research",
		},
		ContentType:     "video",
		ContentIdentity: "work",
		AuthorID:        "builtin_travel_blogger",
		TagRefs:         []string{"Topic/旅行"},
		EntityRefs:      []string{"entity/travel"},
		Angle:           "体验",
		CreatedAt:       now.Add(-2 * time.Hour),
		PublishedAt:     now.Add(-time.Hour),
		UpdatedAt:       now.Add(-time.Minute),
	}

	events, err := releaseimport.BuildImportedPostLifecycleEvents(
		[]releaseimport.PostDoc{post},
		[]releaseimport.ImportedPostDeletionSnapshot{{
			PostID:          "removed-post",
			AuthorID:        "removed-author",
			ContentType:     "image",
			ContentIdentity: "work",
			Status:          "published",
		}},
		releaseimport.ImportOptions{
			ReleaseID:         "release-a",
			ManifestDigest:    "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
			SourceOwner:       "qwq_data",
			ProjectionVersion: 42,
		},
		now,
	)
	if err != nil {
		t.Fatalf("build imported lifecycle: %v", err)
	}
	if len(events) != 2 {
		t.Fatalf("event count=%d, want 2", len(events))
	}
	byType := map[string]int{}
	for index, event := range events {
		byType[event.EventType] = index
		if event.AggregateType != "Post" || event.AggregateVersion != 42 {
			t.Fatalf("unexpected durable event envelope: %#v", event)
		}
	}
	published := events[byType["PostPublished"]]
	if published.AggregateID != releaseimport.RuntimePostID(post.ContentID, post.PostRef) {
		t.Fatalf("unexpected published event: %#v", published)
	}
	var payload map[string]any
	if err := json.Unmarshal(published.Payload, &payload); err != nil {
		t.Fatalf("decode published payload: %v", err)
	}
	if payload["sourceOwner"] != "qwq_data" || payload["releaseId"] != "release-a" ||
		payload["releaseDigest"] == "" {
		t.Fatalf("published event lacks immutable release binding: %#v", payload)
	}
	if payload["contentId"] != "travel_video_candidate" ||
		payload["contentVersion"] != float64(2) || payload["usageScope"] != "research" {
		t.Fatalf("published event lacks content-pool binding: %#v", payload)
	}
	deleted := events[byType["PostDeleted"]]
	if deleted.AggregateID != "removed-post" {
		t.Fatalf("unexpected deleted event: %#v", deleted)
	}
	var deletedPayload map[string]any
	if err := json.Unmarshal(deleted.Payload, &deletedPayload); err != nil {
		t.Fatalf("decode deleted payload: %v", err)
	}
	wantDeletedKeys := []string{
		"authorId", "contentIdentity", "contentType", "deletedAt", "postId", "status",
	}
	gotDeletedKeys := make([]string, 0, len(deletedPayload))
	for key := range deletedPayload {
		gotDeletedKeys = append(gotDeletedKeys, key)
	}
	sort.Strings(gotDeletedKeys)
	if !slices.Equal(gotDeletedKeys, wantDeletedKeys) {
		t.Fatalf("deleted payload keys=%v, want %v", gotDeletedKeys, wantDeletedKeys)
	}
	if deletedPayload["authorId"] != "removed-author" ||
		deletedPayload["contentType"] != "image" ||
		deletedPayload["contentIdentity"] != "work" ||
		deletedPayload["status"] != "published" {
		t.Fatalf("deleted payload lost canonical Post snapshot: %#v", deletedPayload)
	}
}

func TestFourImportedPostTombstonesKeepStableReplayIdentities(t *testing.T) {
	now := time.Date(2026, 8, 11, 3, 10, 0, 0, time.UTC)
	snapshots := make([]releaseimport.ImportedPostDeletionSnapshot, 0, 4)
	for index := 0; index < 4; index++ {
		snapshots = append(snapshots, releaseimport.ImportedPostDeletionSnapshot{
			PostID:          fmt.Sprintf("removed-post-%d", index),
			AuthorID:        fmt.Sprintf("removed-author-%d", index),
			ContentType:     []string{"article", "image", "video", "image"}[index],
			ContentIdentity: "work",
			Status:          "published",
		})
	}
	opts := releaseimport.ImportOptions{
		ReleaseID:         "release-four-tombstones",
		ManifestDigest:    "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
		SourceOwner:       "qwq_data",
		ProjectionVersion: 1786417850129,
	}
	first, err := releaseimport.BuildImportedPostLifecycleEvents(nil, snapshots, opts, now)
	if err != nil {
		t.Fatalf("first tombstone build: %v", err)
	}
	replayed, err := releaseimport.BuildImportedPostLifecycleEvents(nil, snapshots, opts, now)
	if err != nil {
		t.Fatalf("replayed tombstone build: %v", err)
	}
	if len(first) != 4 || len(replayed) != 4 {
		t.Fatalf("tombstone counts first=%d replay=%d, want 4", len(first), len(replayed))
	}
	for index := range first {
		if first[index].EventID != replayed[index].EventID ||
			!slices.Equal(first[index].Payload, replayed[index].Payload) {
			t.Fatalf("tombstone replay drift at %d", index)
		}
	}
}

func TestAlreadyTombstonedPostKeepsPublishedStatusBeforeDelete(t *testing.T) {
	now := time.Date(2026, 8, 11, 22, 45, 50, 701000000, time.UTC)
	events, err := releaseimport.BuildImportedPostLifecycleEvents(
		nil,
		[]releaseimport.ImportedPostDeletionSnapshot{{
			PostID:          "already-tombstoned-post",
			AuthorID:        "release-author",
			ContentType:     "article",
			ContentIdentity: "work",
			Status:          "published",
		}},
		releaseimport.ImportOptions{
			ReleaseID:         "release-retombstone",
			ManifestDigest:    "sha256:" + strings.Repeat("a", 64),
			SourceOwner:       "qwq_data",
			ProjectionVersion: 1786488350701,
		},
		now,
	)
	if err != nil {
		t.Fatal(err)
	}
	var payload map[string]any
	if err := json.Unmarshal(events[0].Payload, &payload); err != nil {
		t.Fatal(err)
	}
	if payload["status"] != "published" {
		t.Fatalf("status-before-delete=%v, want published", payload["status"])
	}
}

func TestFourLegacyPostDeletedEventsRepairOnceAndReplayByteIdentically(
	t *testing.T,
) {
	t.Parallel()
	now := time.Date(2026, 8, 11, 3, 10, 0, 0, time.UTC)
	opts := releaseimport.ImportOptions{
		ReleaseID:         "content-alpha-research-pool-20260811-002",
		ManifestDigest:    "sha256:58895c715e2547414c302b463e683b9878a2f441de7c2642194a5b3329ef83e0",
		SourceOwner:       "qwq_data",
		ProjectionVersion: 1786417850129,
	}
	snapshots := fourDeletionSnapshots()
	events, err := releaseimport.BuildImportedPostLifecycleEvents(nil, snapshots, opts, now)
	if err != nil {
		t.Fatalf("build canonical tombstones: %v", err)
	}
	cas := &outboxPayloadCAS{events: map[string]releaseimport.ImportedPostOutboxEventSnapshot{}}
	for index, event := range events {
		cas.events[event.EventID] = importedOutboxSnapshot(
			t,
			event,
			int64(index+47),
			legacyPostDeletedPayload(t, event, opts),
		)
	}
	if err := releaseimport.ValidateImportedPostDeletionReplayClosure(
		mapsOfOutboxEvents(cas.events),
		events,
		opts,
	); err != nil {
		t.Fatalf("validate four-event replay closure: %v", err)
	}

	audits := make([]releaseimport.ImportedPostOutboxRepairAudit, 0, 4)
	for _, event := range events {
		existing := cas.events[event.EventID]
		audit, err := releaseimport.RepairImportedPostOutboxEvent(
			context.Background(),
			cas,
			existing,
			event,
			opts,
		)
		if err != nil {
			t.Fatalf("repair %s: %v", event.EventID, err)
		}
		if audit == nil {
			t.Fatalf("legacy event %s was not repaired", event.EventID)
		}
		audits = append(audits, *audit)
		got := cas.events[event.EventID]
		if !slices.Equal(got.PayloadJSON, event.Payload) {
			t.Fatalf("repaired payload drift for %s", event.EventID)
		}
		assertImportedOutboxEnvelopeEqual(t, got, existing)
		if audit.BeforeSHA256 != testPayloadSHA256(existing.PayloadJSON) ||
			audit.AfterSHA256 != testPayloadSHA256(event.Payload) {
			t.Fatalf("repair audit digest drift: %+v", audit)
		}
	}
	if len(audits) != 4 || cas.calls != 4 {
		t.Fatalf("repair count audits=%d cas=%d, want 4", len(audits), cas.calls)
	}

	bytesAfterRepair := make(map[string][]byte, len(events))
	for _, event := range events {
		bytesAfterRepair[event.EventID] = append(
			[]byte(nil),
			cas.events[event.EventID].PayloadJSON...,
		)
		audit, err := releaseimport.RepairImportedPostOutboxEvent(
			context.Background(),
			cas,
			cas.events[event.EventID],
			event,
			opts,
		)
		if err != nil || audit != nil {
			t.Fatalf("second replay %s audit=%+v err=%v", event.EventID, audit, err)
		}
		if !slices.Equal(bytesAfterRepair[event.EventID], cas.events[event.EventID].PayloadJSON) {
			t.Fatalf("second replay changed canonical bytes for %s", event.EventID)
		}
	}
	if cas.calls != 4 {
		t.Fatalf("second replay executed CAS: calls=%d want=4", cas.calls)
	}

	for _, result := range []releaseimport.ImportedReleaseApplyResult{
		{
			PostsUpserted:           46,
			PostsRemoved:            0,
			PostDeletionEventsReady: 4,
			OutboxEventsReady:       4,
			OutboxEventsAppended:    0,
			OutboxEventsRepaired:    4,
			Replayed:                true,
			RepairReplay:            true,
		},
		{
			PostsUpserted:           46,
			PostsRemoved:            0,
			PostDeletionEventsReady: 4,
			OutboxEventsReady:       4,
			OutboxEventsAppended:    0,
			OutboxEventsRepaired:    0,
			Replayed:                true,
			RepairReplay:            true,
		},
	} {
		if err := releaseimport.ValidateImportedReleaseApplyResult(result, 46); err != nil {
			t.Fatalf("valid repair replay rejected: %+v err=%v", result, err)
		}
	}
}

func TestIntermediatePostDeletedStatusRepairsByExactCAS(t *testing.T) {
	t.Parallel()
	now := time.Date(2026, 8, 11, 22, 45, 50, 701000000, time.UTC)
	opts := releaseimport.ImportOptions{
		ReleaseID:         "content-alpha-research-pool-20260811-003",
		ManifestDigest:    "sha256:75ea2a68dfda915287a63b32dd4e0b3f2e75784e79bec94fb209c8b54a453611",
		SourceOwner:       "qwq_data",
		ProjectionVersion: 1786488350701,
	}
	events, err := releaseimport.BuildImportedPostLifecycleEvents(
		nil,
		fourDeletionSnapshots()[:1],
		opts,
		now,
	)
	if err != nil {
		t.Fatal(err)
	}
	event := events[0]
	var intermediate map[string]any
	if err := json.Unmarshal(event.Payload, &intermediate); err != nil {
		t.Fatal(err)
	}
	intermediate["status"] = "deleted"
	raw, err := json.Marshal(intermediate)
	if err != nil {
		t.Fatal(err)
	}
	existing := importedOutboxSnapshot(t, event, 104, raw)
	cas := &outboxPayloadCAS{events: map[string]releaseimport.ImportedPostOutboxEventSnapshot{
		event.EventID: existing,
	}}
	audit, err := releaseimport.RepairImportedPostOutboxEvent(
		context.Background(), cas, existing, event, opts,
	)
	if err != nil || audit == nil {
		t.Fatalf("intermediate repair audit=%+v err=%v", audit, err)
	}
	if cas.calls != 1 || !slices.Equal(cas.events[event.EventID].PayloadJSON, event.Payload) {
		t.Fatalf("intermediate repair did not converge: calls=%d", cas.calls)
	}

	intermediate["authorId"] = "other-author"
	drifted, err := json.Marshal(intermediate)
	if err != nil {
		t.Fatal(err)
	}
	unsafe := importedOutboxSnapshot(t, event, 104, drifted)
	blocked := &outboxPayloadCAS{events: map[string]releaseimport.ImportedPostOutboxEventSnapshot{
		event.EventID: unsafe,
	}}
	if _, err := releaseimport.RepairImportedPostOutboxEvent(
		context.Background(), blocked, unsafe, event, opts,
	); err == nil || !strings.Contains(err.Error(), "GATE_BLOCK") {
		t.Fatalf("drifted intermediate payload was accepted: %v", err)
	}
	if blocked.calls != 0 {
		t.Fatalf("drifted intermediate payload reached CAS: %d", blocked.calls)
	}
}

func TestLegacyPostDeletedRepairRejectsUnknownShapeBindingAndMissingSnapshot(
	t *testing.T,
) {
	t.Parallel()
	now := time.Date(2026, 8, 11, 3, 10, 0, 0, time.UTC)
	opts := releaseimport.ImportOptions{
		ReleaseID:         "release-repair-a",
		ManifestDigest:    "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
		SourceOwner:       "qwq_data",
		ProjectionVersion: 42,
	}
	events, err := releaseimport.BuildImportedPostLifecycleEvents(
		nil,
		fourDeletionSnapshots()[:1],
		opts,
		now,
	)
	if err != nil {
		t.Fatal(err)
	}
	event := events[0]
	valid := legacyPostDeletedPayload(t, event, opts)

	var validMap map[string]any
	if err := json.Unmarshal(valid, &validMap); err != nil {
		t.Fatal(err)
	}
	tests := []struct {
		name      string
		mutate    func(map[string]any)
		eventType string
	}{
		{name: "unknown field", mutate: func(value map[string]any) { value["circleIds"] = []string{} }},
		{name: "release drift", mutate: func(value map[string]any) { value["releaseId"] = "other-release" }},
		{name: "digest drift", mutate: func(value map[string]any) { value["releaseDigest"] = "sha256:" + strings.Repeat("b", 64) }},
		{name: "source owner drift", mutate: func(value map[string]any) { value["sourceOwner"] = "other-owner" }},
		{name: "aggregate drift", mutate: func(value map[string]any) { value["postId"] = "other-post" }},
		{name: "occurred at drift", mutate: func(value map[string]any) { value["deletedAt"] = now.Add(time.Second).Format(time.RFC3339Nano) }},
		{name: "non PostDeleted", mutate: func(map[string]any) {}, eventType: "PostPublished"},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			payload := make(map[string]any, len(validMap))
			for key, value := range validMap {
				payload[key] = value
			}
			test.mutate(payload)
			raw, err := json.Marshal(payload)
			if err != nil {
				t.Fatal(err)
			}
			existing := importedOutboxSnapshot(t, event, 47, raw)
			if test.eventType != "" {
				existing.EventType = test.eventType
			}
			cas := &outboxPayloadCAS{events: map[string]releaseimport.ImportedPostOutboxEventSnapshot{
				event.EventID: existing,
			}}
			if _, err := releaseimport.RepairImportedPostOutboxEvent(
				context.Background(), cas, existing, event, opts,
			); err == nil || !strings.Contains(err.Error(), "GATE_BLOCK") {
				t.Fatalf("unsafe legacy event accepted: %v", err)
			}
			if cas.calls != 0 {
				t.Fatalf("unsafe legacy event reached CAS: %d", cas.calls)
			}
		})
	}

	missing := importedOutboxSnapshot(t, event, 47, valid)
	if err := releaseimport.ValidateImportedPostDeletionReplayClosure(
		[]releaseimport.ImportedPostOutboxEventSnapshot{missing},
		nil,
		opts,
	); err == nil || !strings.Contains(err.Error(), "GATE_BLOCK") {
		t.Fatalf("missing replay snapshot was not blocked: %v", err)
	}
}

func TestLegacyPostDeletedRepairCASFailureIsNotAcknowledged(t *testing.T) {
	t.Parallel()
	now := time.Date(2026, 8, 11, 3, 10, 0, 0, time.UTC)
	opts := releaseimport.ImportOptions{
		ReleaseID: "release-repair-cas", ManifestDigest: "sha256:" + strings.Repeat("a", 64),
		SourceOwner: "qwq_data", ProjectionVersion: 43,
	}
	events, err := releaseimport.BuildImportedPostLifecycleEvents(
		nil, fourDeletionSnapshots()[:1], opts, now,
	)
	if err != nil {
		t.Fatal(err)
	}
	event := events[0]
	existing := importedOutboxSnapshot(t, event, 47, legacyPostDeletedPayload(t, event, opts))
	for _, test := range []struct {
		name          string
		forceMismatch bool
		err           error
	}{
		{name: "compare and set mismatch", forceMismatch: true},
		{name: "transaction write failure", err: errors.New("transaction aborted")},
	} {
		t.Run(test.name, func(t *testing.T) {
			cas := &outboxPayloadCAS{
				events:        map[string]releaseimport.ImportedPostOutboxEventSnapshot{event.EventID: existing},
				forceMismatch: test.forceMismatch,
				err:           test.err,
			}
			audit, err := releaseimport.RepairImportedPostOutboxEvent(
				context.Background(), cas, existing, event, opts,
			)
			if err == nil || audit != nil {
				t.Fatalf("failed CAS acknowledged audit=%+v err=%v", audit, err)
			}
			if got := cas.events[event.EventID]; !slices.Equal(got.PayloadJSON, existing.PayloadJSON) {
				t.Fatal("failed transaction changed durable payload")
			}
		})
	}
}

func fourDeletionSnapshots() []releaseimport.ImportedPostDeletionSnapshot {
	snapshots := make([]releaseimport.ImportedPostDeletionSnapshot, 0, 4)
	for index := 0; index < 4; index++ {
		snapshots = append(snapshots, releaseimport.ImportedPostDeletionSnapshot{
			PostID:          fmt.Sprintf("data-post-removed-%d", index),
			AuthorID:        fmt.Sprintf("data-author-%d", index),
			ContentType:     []string{"article", "image", "video", "image"}[index],
			ContentIdentity: "work",
			Status:          "published",
		})
	}
	return snapshots
}

func legacyPostDeletedPayload(
	t *testing.T,
	event postports.OutboxEvent,
	opts releaseimport.ImportOptions,
) []byte {
	t.Helper()
	raw, err := json.Marshal(map[string]any{
		"postId": event.AggregateID, "releaseId": opts.ReleaseID,
		"releaseDigest": opts.ManifestDigest, "sourceOwner": opts.SourceOwner,
		"deletedAt": event.OccurredAt.Format(time.RFC3339Nano),
	})
	if err != nil {
		t.Fatal(err)
	}
	return raw
}

func importedOutboxSnapshot(
	t *testing.T,
	event postports.OutboxEvent,
	sequence int64,
	payload []byte,
) releaseimport.ImportedPostOutboxEventSnapshot {
	t.Helper()
	return releaseimport.ImportedPostOutboxEventSnapshot{
		EventID: event.EventID, OutboxSequence: sequence,
		EventType: event.EventType, AggregateType: event.AggregateType,
		AggregateID: event.AggregateID, AggregateVersion: event.AggregateVersion,
		PayloadJSON: append([]byte(nil), payload...), OccurredAt: event.OccurredAt,
	}
}

func assertImportedOutboxEnvelopeEqual(
	t *testing.T,
	got,
	want releaseimport.ImportedPostOutboxEventSnapshot,
) {
	t.Helper()
	if got.EventID != want.EventID || got.OutboxSequence != want.OutboxSequence ||
		got.EventType != want.EventType || got.AggregateType != want.AggregateType ||
		got.AggregateID != want.AggregateID ||
		got.AggregateVersion != want.AggregateVersion ||
		!got.OccurredAt.Equal(want.OccurredAt) {
		t.Fatalf("repair changed immutable outbox envelope: got=%+v want=%+v", got, want)
	}
}

func testPayloadSHA256(payload []byte) string {
	return fmt.Sprintf("sha256:%x", sha256.Sum256(payload))
}

func mapsOfOutboxEvents(
	values map[string]releaseimport.ImportedPostOutboxEventSnapshot,
) []releaseimport.ImportedPostOutboxEventSnapshot {
	result := make([]releaseimport.ImportedPostOutboxEventSnapshot, 0, len(values))
	for _, value := range values {
		result = append(result, value)
	}
	return result
}

type outboxPayloadCAS struct {
	events        map[string]releaseimport.ImportedPostOutboxEventSnapshot
	forceMismatch bool
	err           error
	calls         int
}

func (c *outboxPayloadCAS) CompareAndSwapImportedPostOutboxPayload(
	_ context.Context,
	existing releaseimport.ImportedPostOutboxEventSnapshot,
	replacement json.RawMessage,
) (bool, error) {
	c.calls++
	if c.err != nil {
		return false, c.err
	}
	current, exists := c.events[existing.EventID]
	matched := !c.forceMismatch && exists &&
		slices.Equal(current.PayloadJSON, existing.PayloadJSON)
	if !matched {
		return false, nil
	}
	current.PayloadJSON = append([]byte(nil), replacement...)
	c.events[existing.EventID] = current
	return true, nil
}

func TestImportedReleaseActivationRequiresExactManifestAndOutboxCounts(t *testing.T) {
	tests := []struct {
		name   string
		result releaseimport.ImportedReleaseApplyResult
		posts  int
		valid  bool
	}{
		{
			name: "first activation",
			result: releaseimport.ImportedReleaseApplyResult{
				PostsUpserted:           3,
				PostsRemoved:            1,
				PostDeletionEventsReady: 1,
				OutboxEventsReady:       4,
				OutboxEventsAppended:    4,
			},
			posts: 3,
			valid: true,
		},
		{
			name: "idempotent replay",
			result: releaseimport.ImportedReleaseApplyResult{
				PostsUpserted:        3,
				OutboxEventsReady:    3,
				OutboxEventsAppended: 0,
				Replayed:             true,
			},
			posts: 3,
			valid: true,
		},
		{
			name: "partial Post import",
			result: releaseimport.ImportedReleaseApplyResult{
				PostsUpserted:        2,
				OutboxEventsReady:    3,
				OutboxEventsAppended: 3,
			},
			posts: 3,
		},
		{
			name: "partial outbox append",
			result: releaseimport.ImportedReleaseApplyResult{
				PostsUpserted:        3,
				OutboxEventsReady:    3,
				OutboxEventsAppended: 2,
			},
			posts: 3,
		},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			err := releaseimport.ValidateImportedReleaseApplyResult(
				test.result,
				test.posts,
			)
			if test.valid && err != nil {
				t.Fatalf("expected valid activation: %v", err)
			}
			if !test.valid && err == nil {
				t.Fatal("partial activation must fail before the active pointer changes")
			}
		})
	}
}
