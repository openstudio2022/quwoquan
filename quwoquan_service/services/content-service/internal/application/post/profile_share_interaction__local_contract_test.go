package post

import (
	"context"
	"fmt"
	"testing"
	"time"

	postdomain "quwoquan_service/services/content-service/internal/domain/post"
	postmodel "quwoquan_service/services/content-service/internal/domain/post/model"
	"quwoquan_service/services/content-service/internal/testsupport"
)

func TestProfileShareInteractionsUseDurableOccurrenceAndStableCursor(t *testing.T) {
	ctx := context.Background()
	now := time.Date(2026, 7, 12, 8, 0, 0, 0, time.UTC)
	postStore := testsupport.NewPostStore([]postmodel.Post{{
		ID:                        "share_target",
		AuthorId:                  "owner",
		AuthorDisplayNameSnapshot: "主页作者",
		ContentType:               "image",
		Title:                     "川西晨光",
		CoverUrl:                  "media/share_target.png",
		Status:                    "published",
		Visibility:                "public",
		CreatedAt:                 now,
		UpdatedAt:                 now,
		PublishedAt:               now,
	}})
	shareStore := testsupport.NewShareInteractionStore()
	service := NewPostService(
		BindDataPorts(postStore),
		WithShareInteractionStore(shareStore),
	)

	if err := shareStore.Save(ctx, postdomain.ShareInteractionOccurrence{
		InteractionID: "outbound-share", ActorSubAccountID: "actor",
		TargetSubAccountID: "owner", TargetContentID: "share_target",
		TargetContentType: "image", TargetKind: "record", TargetAvailability: "active",
		OccurredAt: now,
	}); err != nil {
		t.Fatalf("seed outbound share projection: %v", err)
	}
	received, _, _, err := service.ListProfileShareInteractions(
		ctx,
		"owner",
		"received",
		"",
		20,
	)
	if err != nil || len(received) != 1 {
		t.Fatalf("received history mismatch items=%d err=%v", len(received), err)
	}
	if received[0].ActivityType != "share" ||
		received[0].TargetKind != "record" ||
		received[0].TargetContentId != "share_target" ||
		received[0].OccurredAt.IsZero() {
		t.Fatalf("received projection mismatch: %#v", received[0])
	}
	sent, _, _, err := service.ListProfileShareInteractions(
		ctx,
		"actor",
		"sent",
		"",
		20,
	)
	if err != nil || len(sent) != 1 || sent[0].ImpactPrimaryText != "" {
		t.Fatalf("initiated projection mismatch: %#v err=%v", sent, err)
	}

	for index := 0; index < 21; index++ {
		id := fmt.Sprintf("share-page-%02d", index)
		if err := shareStore.Save(ctx, postdomain.ShareInteractionOccurrence{
			InteractionID:        id,
			ActorSubAccountID:    fmt.Sprintf("actor-%02d", index),
			TargetSubAccountID:   "paged-owner",
			TargetContentID:      "share_target",
			TargetContentType:    "image",
			TargetKind:           "record",
			TargetAvailability:   "active",
			PreviewMediaKind:     "image",
			ImpactPrimaryText:    "带来真实浏览",
			ImpactDeepLink:       "myIntersections",
			OutboundShareEventID: id,
			OccurredAt:           now,
		}); err != nil {
			t.Fatalf("seed occurrence: %v", err)
		}
	}
	first, cursor, hasMore, err := service.ListProfileShareInteractions(
		ctx,
		"paged-owner",
		"received",
		"",
		20,
	)
	if err != nil || len(first) != 20 || !hasMore || cursor == "" {
		t.Fatalf("first cursor page mismatch items=%d more=%v cursor=%q err=%v", len(first), hasMore, cursor, err)
	}
	second, _, hasMore, err := service.ListProfileShareInteractions(
		ctx,
		"paged-owner",
		"received",
		cursor,
		20,
	)
	if err != nil || len(second) != 1 || hasMore {
		t.Fatalf("second cursor page mismatch items=%d more=%v err=%v", len(second), hasMore, err)
	}
	seen := map[string]bool{}
	for _, item := range append(first, second...) {
		if seen[item.ActivityId] {
			t.Fatalf("duplicate interaction across cursor pages: %s", item.ActivityId)
		}
		seen[item.ActivityId] = true
	}

	target := first[0]
	if err := service.MarkProfileShareInteractionState(
		ctx,
		"paged-owner",
		target.ActivityId,
		"read",
	); err != nil {
		t.Fatalf("mark read: %v", err)
	}
	refreshed, _, _, err := service.ListProfileShareInteractions(
		ctx,
		"paged-owner",
		"received",
		"",
		20,
	)
	if err != nil || refreshed[0].ReadAt.IsZero() || refreshed[0].SeenAt.IsZero() {
		t.Fatalf("read/seen idempotent state missing: %#v err=%v", refreshed[0], err)
	}
}

func TestProfileShareInteractionRejectsMalformedCursor(t *testing.T) {
	service := NewPostService(
		BindDataPorts(testsupport.NewPostStore(nil)),
		WithShareInteractionStore(testsupport.NewShareInteractionStore()),
	)
	_, _, _, err := service.ListProfileShareInteractions(
		context.Background(),
		"owner",
		"received",
		"not-a-cursor",
		20,
	)
	if err == nil {
		t.Fatal("expected malformed cursor to fail")
	}
}
