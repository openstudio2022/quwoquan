package post

import (
	"context"
	"sync"
	"testing"

	"quwoquan_service/services/content-service/internal/application/commandmeta"
	postmodel "quwoquan_service/services/content-service/internal/domain/post/model"
	"quwoquan_service/services/content-service/internal/testsupport"
)

func TestSubmitPostPublicationReplayReturnsOriginalPost(t *testing.T) {
	store := testsupport.NewPostStore(nil)
	service := NewPostService(BindDataPorts(store))
	command := testPublicationCommand("intent-replay", "draft-replay")

	first, err := service.SubmitPostPublication(
		commandmeta.WithIdempotencyKey(context.Background(), "intent-replay"),
		command,
	)
	if err != nil {
		t.Fatal(err)
	}
	command.Content.Body = "replayed payload must not replace published content"
	replayed, err := service.SubmitPostPublication(
		commandmeta.WithIdempotencyKey(context.Background(), "intent-replay"),
		command,
	)
	if err != nil {
		t.Fatal(err)
	}
	if first != replayed || first.CommittedVersion != 1 ||
		first.State != "published" {
		t.Fatalf("publication receipt changed on replay: first=%+v replay=%+v", first, replayed)
	}
	stored, found := store.FindByID(context.Background(), first.PostID)
	if !found || stored.Body != "first publication" {
		t.Fatalf("published aggregate was replaced by replay: %+v", stored)
	}
	if events := store.OutboxEvents(); len(events) != 1 ||
		events[0].EventType != "PostPublished" {
		t.Fatalf("expected exactly one PostPublished event, got %+v", events)
	}
}

func TestSubmitPostPublicationNewIntentForPublishedDraftIsIgnored(t *testing.T) {
	store := testsupport.NewPostStore(nil)
	service := NewPostService(BindDataPorts(store))
	first, err := service.SubmitPostPublication(
		commandmeta.WithIdempotencyKey(context.Background(), "intent-original"),
		testPublicationCommand("intent-original", "draft-once"),
	)
	if err != nil {
		t.Fatal(err)
	}
	second, err := service.SubmitPostPublication(
		commandmeta.WithIdempotencyKey(context.Background(), "intent-accidental"),
		testPublicationCommand("intent-accidental", "draft-once"),
	)
	if err != nil {
		t.Fatal(err)
	}
	if second != first {
		t.Fatalf("published draft must return original receipt: first=%+v second=%+v", first, second)
	}
	if len(store.OutboxEvents()) != 1 {
		t.Fatalf("published draft created duplicate outbox events")
	}
}

func TestSubmitPostPublicationConcurrentReplayCreatesOnePost(t *testing.T) {
	store := testsupport.NewPostStore(nil)
	service := NewPostService(BindDataPorts(store))
	command := testPublicationCommand("intent-concurrent", "draft-concurrent")

	const workers = 16
	results := make(chan PostPublicationReceipt, workers)
	failures := make(chan error, workers)
	var group sync.WaitGroup
	for range workers {
		group.Add(1)
		go func() {
			defer group.Done()
			receipt, err := service.SubmitPostPublication(
				commandmeta.WithIdempotencyKey(
					context.Background(),
					"intent-concurrent",
				),
				command,
			)
			if err != nil {
				failures <- err
				return
			}
			results <- receipt
		}()
	}
	group.Wait()
	close(results)
	close(failures)
	for err := range failures {
		t.Fatalf("concurrent publication failed: %v", err)
	}
	var postID string
	count := 0
	for receipt := range results {
		count++
		if postID == "" {
			postID = receipt.PostID
		}
		if receipt.PostID != postID || receipt.CommittedVersion != 1 {
			t.Fatalf("concurrent replay returned divergent receipt: %+v", receipt)
		}
	}
	if count != workers || len(store.OutboxEvents()) != 1 {
		t.Fatalf("expected %d receipts and one event, got %d and %d", workers, count, len(store.OutboxEvents()))
	}
}

func TestSubmitPostPublicationBindsReadyOwnedMedia(t *testing.T) {
	store := testsupport.NewPostStore(nil)
	media := &publicationMediaReader{
		assets: map[string]MediaAssetBindingSlice{
			"asset-image": {
				AssetID:        "asset-image",
				OwnerID:        "persona-media",
				Ready:          true,
				MediaType:      "image",
				PublicSliceKey: "media/image/public/asset-image",
			},
		},
	}
	ports := WithMediaAssetBindingReader(BindDataPorts(store), media)
	service := NewPostService(ports)
	command := SubmitPostPublicationCommand{
		PublishIntentID: "intent-media",
		LocalDraftID:    "draft-media",
		AuthorID:        "persona-media",
		Content: postmodel.Post{
			ContentType:   "image",
			MediaAssetIds: []string{"asset-image"},
			Visibility:    "public",
		},
	}
	receipt, err := service.SubmitPostPublication(
		commandmeta.WithIdempotencyKey(context.Background(), "intent-media"),
		command,
	)
	if err != nil {
		t.Fatal(err)
	}
	stored, found := store.FindByID(context.Background(), receipt.PostID)
	if !found || len(stored.MediaAssetIds) != 1 || len(stored.MediaUrls) != 1 ||
		stored.MediaUrls[0] != "media/image/public/asset-image" ||
		media.materializeCalls != 1 {
		t.Fatalf("media publication was not atomically projected: post=%+v media=%+v", stored, media)
	}
}

func testPublicationCommand(intentID, draftID string) SubmitPostPublicationCommand {
	return SubmitPostPublicationCommand{
		PublishIntentID: intentID,
		LocalDraftID:    draftID,
		AuthorID:        "persona-publication",
		Content: postmodel.Post{
			ContentType: "micro",
			Body:        "first publication",
			Visibility:  "public",
		},
	}
}

type publicationMediaReader struct {
	assets           map[string]MediaAssetBindingSlice
	materializeCalls int
}

func (r *publicationMediaReader) FindMediaAssetsForBinding(
	_ context.Context,
	_ []string,
) (map[string]MediaAssetBindingSlice, error) {
	return r.assets, nil
}

func (r *publicationMediaReader) MaterializePublicSlices(
	_ context.Context,
	_ []string,
) error {
	r.materializeCalls++
	return nil
}
