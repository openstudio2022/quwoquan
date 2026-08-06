// spec_ref: specs/feature-tree/discovery-content/media-processing-helper-read/image-delivery-variants/spec.md#gwt-003
// readiness_case: request-original-image-access-local
package application_test

import (
	"context"
	"fmt"
	"testing"
	"time"

	"quwoquan_service/runtime/commandmeta"
	mediaassetports "quwoquan_service/services/content-service/internal/media/media_asset/domain/ports"
	originalaccessapp "quwoquan_service/services/content-service/internal/media/media_original_access_fact/application"
	originalaccessmodel "quwoquan_service/services/content-service/internal/media/media_original_access_fact/domain/model"
	originalaccessports "quwoquan_service/services/content-service/internal/media/media_original_access_fact/domain/ports"
)

func TestRequestOriginalImageAccessExecutesTheApplicationBoundary(t *testing.T) {
	now := time.Date(2030, time.September, 10, 11, 12, 13, 0, time.UTC)
	store := &memoryOriginalAccessStore{facts: map[string]originalaccessmodel.Fact{}}
	service := originalaccessapp.NewService(
		store,
		readyOriginalAccessAsset{},
		visibleOriginalAccessPost{},
		originalAccessSigner{},
		originalaccessapp.WithClock(func() time.Time { return now }),
	)
	ctx := commandmeta.WithIdempotencyKey(context.Background(), "original-access-local")
	command := originalaccessapp.Command{
		AssetID: "media-original-local", ViewerID: "persona-original-owner", Purpose: "save",
	}
	first, err := service.Request(ctx, command)
	if err != nil {
		t.Fatalf("request original image access: %v", err)
	}
	replayed, err := service.Request(ctx, command)
	if err != nil {
		t.Fatalf("replay original image access: %v", err)
	}
	if first.AssetID != command.AssetID || first.Status != "granted" ||
		first.OriginalURL == "" || first.AuditID == "" || first.ExpiresAt != now.Add(5*time.Minute) {
		t.Fatalf("original access result drift: %+v", first)
	}
	if replayed != first || len(store.facts) != 1 || store.appendCalls != 2 {
		t.Fatalf("original access replay drift: first=%+v replay=%+v facts=%d calls=%d", first, replayed, len(store.facts), store.appendCalls)
	}
}

type memoryOriginalAccessStore struct {
	facts       map[string]originalaccessmodel.Fact
	appendCalls int
}

func (store *memoryOriginalAccessStore) Append(
	_ context.Context,
	request originalaccessports.AppendRequest,
) (originalaccessports.AppendResult, error) {
	store.appendCalls++
	key := request.Fact.IdempotencyKey
	if existing, found := store.facts[key]; found {
		return originalaccessports.AppendResult{Fact: existing, Replayed: true}, nil
	}
	store.facts[key] = request.Fact
	return originalaccessports.AppendResult{Fact: request.Fact}, nil
}

type readyOriginalAccessAsset struct{}

func (readyOriginalAccessAsset) FindOriginalAccessAsset(
	context.Context,
	string,
) (mediaassetports.OriginalAccessSlice, bool, error) {
	return mediaassetports.OriginalAccessSlice{
		AssetID: "media-original-local", OwnerID: "persona-original-owner",
		ObjectKey: "media/original/local.jpg", MediaType: "image", MimeType: "image/jpeg",
		FileSize: 512, ProcessingStatus: "ready", AccessPolicy: "owner_only",
	}, true, nil
}

type visibleOriginalAccessPost struct{}

func (visibleOriginalAccessPost) CanViewerAccessPublishedMedia(
	context.Context,
	string,
	string,
) (bool, error) {
	return true, nil
}

type originalAccessSigner struct{}

func (originalAccessSigner) DeliveryURLUntil(
	_ context.Context,
	objectKey string,
	expiresAt time.Time,
) (string, error) {
	return fmt.Sprintf("https://cdn.example.test/%s?expires=%d", objectKey, expiresAt.Unix()), nil
}
