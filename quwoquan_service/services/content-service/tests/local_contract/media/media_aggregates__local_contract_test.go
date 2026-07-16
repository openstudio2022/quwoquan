package media_test

import (
	"context"
	"fmt"
	"strings"
	"testing"
	"time"

	"quwoquan_service/services/content-service/internal/application/commandmeta"
	mediaapp "quwoquan_service/services/content-service/internal/application/media"
	mediamodel "quwoquan_service/services/content-service/internal/domain/media/model"
	mediacontract "quwoquan_service/services/content-service/internal/testsupport/media_contract"
)

const (
	digestOwner  = "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
	digestExpiry = "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
	digestAtomic = "sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"
)

func TestMediaUploadSessionOwnerExpiryAndStateContracts(t *testing.T) {
	now := time.Date(2030, time.January, 2, 3, 4, 5, 0, time.UTC)
	service, _, clock := newMediaService(now)

	created, err := service.InitMediaUpload(
		mediaContext("init-owner"),
		mediaapp.InitMediaUploadCommand{
			OwnerID:        "persona-owner",
			MediaType:      "image",
			ContentType:    "image/jpeg",
			FileSize:       128,
			ExpectedSHA256: digestOwner,
		},
	)
	if err != nil {
		t.Fatalf("init upload: %v", err)
	}
	if _, err := service.GetMediaUploadSession(context.Background(), mediaapp.GetMediaUploadSessionQuery{
		SessionID: created.SessionID,
		OwnerID:   "persona-other",
	}); err == nil {
		t.Fatal("cross-owner upload-session read must be denied")
	}
	if _, err := service.CompleteMediaUpload(
		mediaContext("complete-wrong-owner"),
		mediaapp.CompleteMediaUploadCommand{
			SessionID:    created.SessionID,
			OwnerID:      "persona-other",
			AccessPolicy: mediamodel.AccessPolicyOwnerOnly,
		},
	); err == nil || !strings.Contains(err.Error(), "unauthorized") {
		t.Fatalf("cross-owner complete must be unauthorized, got %v", err)
	}
	aborted, err := service.AbortMediaUpload(
		mediaContext("abort-owner"),
		mediaapp.AbortMediaUploadCommand{
			SessionID: created.SessionID,
			OwnerID:   "persona-owner",
		},
	)
	if err != nil {
		t.Fatalf("abort pending upload: %v", err)
	}
	if aborted.Status != mediamodel.UploadSessionAborted || aborted.Version != 2 {
		t.Fatalf("unexpected aborted session: %+v", aborted)
	}
	if _, err := service.CompleteMediaUpload(
		mediaContext("complete-aborted"),
		mediaapp.CompleteMediaUploadCommand{
			SessionID:    created.SessionID,
			OwnerID:      "persona-owner",
			AccessPolicy: mediamodel.AccessPolicyOwnerOnly,
		},
	); err == nil {
		t.Fatal("aborted upload must reject complete transition")
	}

	expiring, err := service.InitMediaUpload(
		mediaContext("init-expiring"),
		mediaapp.InitMediaUploadCommand{
			OwnerID:        "persona-owner",
			MediaType:      "image",
			ContentType:    "image/jpeg",
			FileSize:       64,
			ExpectedSHA256: digestExpiry,
		},
	)
	if err != nil {
		t.Fatalf("init expiring upload: %v", err)
	}
	*clock = now.Add(16 * time.Minute)
	if _, err := service.CompleteMediaUpload(
		mediaContext("complete-expired"),
		mediaapp.CompleteMediaUploadCommand{
			SessionID:    expiring.SessionID,
			OwnerID:      "persona-owner",
			AccessPolicy: mediamodel.AccessPolicyOwnerOnly,
		},
	); err == nil {
		t.Fatal("expired upload must reject complete transition")
	}
}

func TestMediaCompleteIsIdempotentAndOutboxVersionsAreAtomic(t *testing.T) {
	now := time.Date(2030, time.February, 3, 4, 5, 6, 0, time.UTC)
	service, store, _ := newMediaService(now)
	created, err := service.InitMediaUpload(
		mediaContext("init-complete"),
		mediaapp.InitMediaUploadCommand{
			OwnerID:        "persona-owner",
			MediaType:      "image",
			ContentType:    "image/jpeg",
			FileSize:       256,
			ExpectedSHA256: digestAtomic,
		},
	)
	if err != nil {
		t.Fatalf("init upload: %v", err)
	}
	command := mediaapp.CompleteMediaUploadCommand{
		SessionID:    created.SessionID,
		OwnerID:      "persona-owner",
		AccessPolicy: mediamodel.AccessPolicyOwnerOnly,
	}
	completeContext := mediaContext("complete-atomic")
	completed, err := service.CompleteMediaUpload(completeContext, command)
	if err != nil {
		t.Fatalf("complete upload: %v", err)
	}
	replayed, err := service.CompleteMediaUpload(completeContext, command)
	if err != nil {
		t.Fatalf("replay complete upload: %v", err)
	}
	if !replayed.Replayed ||
		replayed.SessionID != completed.SessionID ||
		replayed.AssetID != completed.AssetID {
		t.Fatalf("duplicate complete must replay exact result: %+v", replayed)
	}
	events := store.OutboxEvents()
	if len(events) != 3 {
		t.Fatalf("expected init plus one session and one asset fact, got %d", len(events))
	}
	if events[1].AggregateType != "MediaUploadSession" ||
		events[1].AggregateVersion != 2 ||
		events[2].AggregateType != "MediaAsset" ||
		events[2].AggregateVersion != 1 {
		t.Fatalf("completion outbox versions are wrong: %+v", events)
	}
	if _, err := service.GetMediaAsset(context.Background(), mediaapp.GetMediaAssetQuery{
		AssetID: completed.AssetID,
		OwnerID: "persona-other",
	}); err == nil {
		t.Fatal("cross-owner media-asset read must be denied")
	}
	if _, err := service.UpdateMediaAssetAccessPolicy(
		mediaContext("asset-policy-wrong-owner"),
		mediaapp.UpdateMediaAssetAccessPolicyCommand{
			AssetID:      completed.AssetID,
			OwnerID:      "persona-other",
			AccessPolicy: mediamodel.AccessPolicyPublic,
		},
	); err == nil || !strings.Contains(err.Error(), "unauthorized") {
		t.Fatalf("cross-owner asset policy update must be unauthorized, got %v", err)
	}
}

func TestOriginalMediaAccessAppendsOneFactAndKeepsAbsoluteExpiryOnReplay(t *testing.T) {
	now := time.Date(2030, time.March, 4, 5, 6, 7, 0, time.UTC)
	service, store, _ := newMediaService(now)
	created, err := service.InitMediaUpload(
		mediaContext("init-original-access"),
		mediaapp.InitMediaUploadCommand{
			OwnerID: "persona-owner", MediaType: "image", ContentType: "image/jpeg",
			FileSize: 256, ExpectedSHA256: digestAtomic,
		},
	)
	if err != nil {
		t.Fatalf("init upload: %v", err)
	}
	completed, err := service.CompleteMediaUpload(
		mediaContext("complete-original-access"),
		mediaapp.CompleteMediaUploadCommand{
			SessionID: created.SessionID, OwnerID: "persona-owner",
			AccessPolicy: mediamodel.AccessPolicyOwnerOnly,
		},
	)
	if err != nil {
		t.Fatalf("complete upload: %v", err)
	}
	command := mediaapp.RequestOriginalMediaAccessCommand{
		AssetID: completed.AssetID, ViewerID: "persona-owner", Purpose: "save",
	}
	ctx := mediaContext("grant-original-access")
	first, err := service.RequestOriginalMediaAccess(ctx, command)
	if err != nil {
		t.Fatalf("request original access: %v", err)
	}
	replayed, err := service.RequestOriginalMediaAccess(ctx, command)
	if err != nil {
		t.Fatalf("replay original access: %v", err)
	}
	if first.AuditID != replayed.AuditID || first.OriginalURL != replayed.OriginalURL || !first.ExpiresAt.Equal(replayed.ExpiresAt) {
		t.Fatalf("idempotent replay extended or changed grant: first=%+v replay=%+v", first, replayed)
	}
	if !first.ExpiresAt.Equal(now.Add(5*time.Minute)) || !strings.Contains(first.OriginalURL, fmt.Sprintf("expires=%d", first.ExpiresAt.Unix())) {
		t.Fatalf("signed URL and response must share the absolute expiry: %+v", first)
	}
	facts := store.OriginalAccessFacts()
	if len(facts) != 1 || facts[0].AuditID != first.AuditID || facts[0].Purpose != "save" {
		t.Fatalf("expected exactly one durable original access fact, got %+v", facts)
	}
}

func newMediaService(
	now time.Time,
) (*mediaapp.MediaService, *mediacontract.MediaStore, *time.Time) {
	store := mediacontract.NewMediaStore()
	current := new(time.Time)
	*current = now
	identifier := 0
	service := mediaapp.NewMediaService(
		mediaapp.BindDataPorts(store),
		&mediaObjectGateway{now: func() time.Time { return *current }},
		mediaapp.WithClock(func() time.Time { return *current }),
		mediaapp.WithIdentifierGenerator(func(prefix string) (string, error) {
			identifier++
			return prefix + "-" + string(rune('0'+identifier)), nil
		}),
	)
	return service, store, current
}

type mediaObjectGateway struct {
	now func() time.Time
}

func (g *mediaObjectGateway) PrepareUpload(_ context.Context, params mediaapp.PrepareUploadParams) (mediaapp.UploadGrant, error) {
	return mediaapp.UploadGrant{
		ObjectKey: "uploads/" + params.SessionID,
		UploadURL: "https://upload.example.test/" + params.SessionID,
		ExpiresAt: params.ExpiresAt,
	}, nil
}

func (g *mediaObjectGateway) UploadURL(_ context.Context, objectKey string, _ string, _ string, expiresAt time.Time) (string, error) {
	if !expiresAt.After(g.now()) {
		return "", fmt.Errorf("upload grant expired")
	}
	return "https://upload.example.test/" + objectKey, nil
}

func (g *mediaObjectGateway) CompleteUpload(_ context.Context, params mediaapp.CompleteUploadParams) (mediaapp.CompletedUploadObject, error) {
	return mediaapp.CompletedUploadObject{
		ObjectKey:   "media/objects/" + strings.TrimPrefix(params.ExpectedSHA256, "sha256:"),
		SHA256:      params.ExpectedSHA256,
		DeliveryURL: "https://cdn.example.test/media",
	}, nil
}

func (g *mediaObjectGateway) DeliveryURL(_ context.Context, objectKey string) (string, error) {
	return "https://cdn.example.test/" + objectKey, nil
}

func (g *mediaObjectGateway) DeliveryURLUntil(_ context.Context, objectKey string, expiresAt time.Time) (string, error) {
	return fmt.Sprintf("https://cdn.example.test/%s?expires=%d", objectKey, expiresAt.UTC().Unix()), nil
}

func mediaContext(key string) context.Context {
	return commandmeta.WithIdempotencyKey(context.Background(), key)
}
