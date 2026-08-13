// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/text-post-commercial-publication/spec.md#gwt-003
package post_test

import (
	"context"
	. "quwoquan_service/services/content-service/internal/content/post/application"
	"sync"
	"testing"
	"time"

	"quwoquan_service/runtime/commandmeta"
	postmodel "quwoquan_service/services/content-service/generated/content/post/contract/model"
	contentgenerated "quwoquan_service/services/content-service/generated/media/media_asset"
	"quwoquan_service/services/content-service/internal/content/post/infrastructure/testsupport"
	mediamodel "quwoquan_service/services/content-service/internal/media/media_asset/domain/model"
)

func TestSubmitPostPublicationReplayReturnsOriginalPost(t *testing.T) {
	store := testsupport.NewPostStore(nil)
	service := NewPostService(
		BindDataPorts(store),
		WithPublicationAdmission(
			testsupport.AllowPublicationRateGate{},
			testsupport.FixedPublicationSafetyGate{},
		),
	)
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
	service := NewPostService(
		BindDataPorts(store),
		WithPublicationAdmission(
			testsupport.AllowPublicationRateGate{},
			testsupport.FixedPublicationSafetyGate{},
		),
	)
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
	service := NewPostService(
		BindDataPorts(store),
		WithPublicationAdmission(
			testsupport.AllowPublicationRateGate{},
			testsupport.FixedPublicationSafetyGate{},
		),
	)
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
	service := NewPostService(
		ports,
		WithPublicationAdmission(
			testsupport.AllowPublicationRateGate{},
			testsupport.FixedPublicationSafetyGate{},
		),
	)
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

func TestSubmitPostPublicationProjectsOnlyDisclosedCaptureMetadata(t *testing.T) {
	focal := 24.0
	aperture := 1.8
	latitude, longitude := 31.0, 102.0
	capturedAt := time.Date(2026, 5, 2, 10, 0, 0, 0, time.UTC)
	store := testsupport.NewPostStore(nil)
	media := &publicationMediaReader{
		assets: map[string]MediaAssetBindingSlice{
			"asset-capture": {
				AssetID: "asset-capture", OwnerID: "persona-capture", Ready: true,
				MediaType: "image", PublicSliceKey: "media/image/public/asset-capture",
				CaptureMetadata: mediamodel.CaptureMetadata{
					CameraMake: "SONY", CameraModel: "ILCE-7M4",
					LensModel: "FE 24-70mm F2.8 GM II", FocalLengthMM: &focal,
					ApertureFNumber: &aperture, CapturedAt: &capturedAt,
					GPSLatitude: &latitude, GPSLongitude: &longitude,
				},
			},
		},
	}
	service := NewPostService(
		WithMediaAssetBindingReader(BindDataPorts(store), media),
		WithPublicationAdmission(
			testsupport.AllowPublicationRateGate{},
			testsupport.FixedPublicationSafetyGate{},
		),
	)
	command := SubmitPostPublicationCommand{
		PublishIntentID: "intent-capture", LocalDraftID: "draft-capture",
		AuthorID: "persona-capture",
		Content: postmodel.Post{
			ContentType: "image", MediaAssetIds: []string{"asset-capture"},
			Visibility: "public", CaptureDisclosure: []string{"parameters"},
			CaptureFeatureRefs: []string{"client-must-not-own-this-projection"},
		},
	}
	receipt, err := service.SubmitPostPublication(
		commandmeta.WithIdempotencyKey(context.Background(), command.PublishIntentID),
		command,
	)
	if err != nil {
		t.Fatal(err)
	}
	stored, found := store.FindByID(context.Background(), receipt.PostID)
	if !found {
		t.Fatal("published post was not stored")
	}
	want := map[string]bool{
		"Topic/摄影/拍摄参数/焦段/广角":    true,
		"Topic/摄影/拍摄参数/光圈/大光圈虚化": true,
	}
	if len(stored.CaptureFeatureRefs) != len(want) {
		t.Fatalf("capture features=%v, want only disclosed parameter features", stored.CaptureFeatureRefs)
	}
	for _, tag := range stored.CaptureFeatureRefs {
		if !want[tag] {
			t.Fatalf("unexpected undisclosed capture tag %q", tag)
		}
	}
}

func TestSubmitPostPublicationRejectsUnknownCaptureDisclosureBeforeMaterialize(t *testing.T) {
	store := testsupport.NewPostStore(nil)
	media := &publicationMediaReader{assets: map[string]MediaAssetBindingSlice{
		"asset-capture": {
			AssetID: "asset-capture", OwnerID: "persona-capture", Ready: true,
			MediaType: "image", PublicSliceKey: "media/image/public/asset-capture",
		},
	}}
	service := NewPostService(
		WithMediaAssetBindingReader(BindDataPorts(store), media),
		WithPublicationAdmission(
			testsupport.AllowPublicationRateGate{},
			testsupport.FixedPublicationSafetyGate{},
		),
	)
	command := SubmitPostPublicationCommand{
		PublishIntentID: "intent-capture-invalid", LocalDraftID: "draft-capture-invalid",
		AuthorID: "persona-capture",
		Content: postmodel.Post{
			ContentType: "image", MediaAssetIds: []string{"asset-capture"},
			Visibility: "public", CaptureDisclosure: []string{"raw_exif"},
		},
	}
	if _, err := service.SubmitPostPublication(
		commandmeta.WithIdempotencyKey(context.Background(), command.PublishIntentID),
		command,
	); err == nil {
		t.Fatal("unknown capture disclosure must be rejected")
	}
	if media.materializeCalls != 0 {
		t.Fatalf("invalid disclosure materialized media %d time(s)", media.materializeCalls)
	}
}

func TestSubmitPostPublicationDistinguishesProcessingFromRejectedMedia(t *testing.T) {
	for _, testCase := range []struct {
		name         string
		processing   string
		expectedCode string
	}{
		{
			name:         "processing remains retryable",
			processing:   "processing",
			expectedCode: contentgenerated.ErrMediaNotReady.Error(),
		},
		{
			name:         "rejected requires replacement",
			processing:   "rejected",
			expectedCode: contentgenerated.ErrMediaProcessingRejected.Error(),
		},
	} {
		t.Run(testCase.name, func(t *testing.T) {
			store := testsupport.NewPostStore(nil)
			media := &publicationMediaReader{
				assets: map[string]MediaAssetBindingSlice{
					"asset-image": {
						AssetID:          "asset-image",
						OwnerID:          "persona-media",
						ProcessingStatus: testCase.processing,
						MediaType:        "image",
					},
				},
			}
			service := NewPostService(
				WithMediaAssetBindingReader(BindDataPorts(store), media),
				WithPublicationAdmission(
					testsupport.AllowPublicationRateGate{},
					testsupport.FixedPublicationSafetyGate{},
				),
			)
			command := SubmitPostPublicationCommand{
				PublishIntentID: "intent-media-" + testCase.processing,
				LocalDraftID:    "draft-media-" + testCase.processing,
				AuthorID:        "persona-media",
				Content: postmodel.Post{
					ContentType:   "image",
					MediaAssetIds: []string{"asset-image"},
					Visibility:    "public",
				},
			}

			_, err := service.SubmitPostPublication(
				commandmeta.WithIdempotencyKey(
					context.Background(),
					command.PublishIntentID,
				),
				command,
			)

			requirePublicationErrorCode(t, err, testCase.expectedCode)
			if posts, _ := store.ListAll(context.Background()); len(posts) != 0 {
				t.Fatalf("media precondition failure persisted a Post: %+v", posts)
			}
			if media.materializeCalls != 0 {
				t.Fatalf("non-ready media was materialized")
			}
		})
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
