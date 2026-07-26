package objectstorage_test

import (
	"context"
	"strings"
	"testing"
	"time"

	runtimemedia "quwoquan_service/runtime/media"
	sessionapp "quwoquan_service/services/content-service/internal/media/media_upload_session/application"
	. "quwoquan_service/services/content-service/internal/media/media_upload_session/infrastructure/objectstorage"
)

const objectDigest = "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"

func TestGatewayVerifiesObjectBeforeCASPromotion(t *testing.T) {
	now := time.Date(2030, time.January, 1, 0, 0, 0, 0, time.UTC)
	client := &objectClientStub{info: &runtimemedia.ObjectInfo{
		Exists: true, Sha256: objectDigest, ContentType: "image/jpeg", Size: 128,
	}}
	gateway := newGateway(t, client, now)
	grant, err := gateway.PrepareUpload(
		context.Background(),
		sessionapp.PrepareUploadParams{
			SessionID: "mus-1", OwnerID: "persona-1", MediaType: "image",
			ContentType: "image/jpeg", FileSize: 128,
			ExpectedSHA256: objectDigest, ExpiresAt: now.Add(15 * time.Minute),
		},
	)
	if err != nil {
		t.Fatalf("prepare upload: %v", err)
	}
	if grant.UploadURL == "" || strings.Contains(grant.ObjectKey, "persona-1") {
		t.Fatalf("upload grant must not leak owner id: %+v", grant)
	}
	completed, err := gateway.CompleteUpload(
		context.Background(),
		sessionapp.CompleteUploadParams{
			ObjectKey: grant.ObjectKey, ExpectedSHA256: objectDigest,
			MediaType: "image", ContentType: "image/jpeg", FileSize: 128,
		},
	)
	if err != nil {
		t.Fatalf("complete upload: %v", err)
	}
	if !strings.HasPrefix(
		completed.ObjectKey,
		"media/objects/sha256/aa/aa/",
	) || client.promotedTo != completed.ObjectKey ||
		client.promotionMetadata["content-type"] != "image/jpeg" {
		t.Fatalf(
			"completion must promote to canonical CAS key with content type: result=%+v promoted=%s metadata=%v",
			completed,
			client.promotedTo,
			client.promotionMetadata,
		)
	}
}

func TestGatewayCompletesFromPromotedCASObjectAfterTransactionRetry(t *testing.T) {
	now := time.Date(2030, time.January, 1, 0, 0, 0, 0, time.UTC)
	discoveryClient := &objectClientStub{info: &runtimemedia.ObjectInfo{
		Exists: true, Sha256: objectDigest, ContentType: "image/jpeg", Size: 128,
	}}
	params := sessionapp.CompleteUploadParams{
		ObjectKey: "uploads/mus-retry.jpg", ExpectedSHA256: objectDigest,
		MediaType: "image", ContentType: "image/jpeg", FileSize: 128,
	}
	if _, err := newGateway(t, discoveryClient, now).CompleteUpload(
		context.Background(),
		params,
	); err != nil {
		t.Fatalf("discover promoted key: %v", err)
	}
	finalKey := discoveryClient.promotedTo
	retryClient := &objectClientStub{infoByKey: map[string]*runtimemedia.ObjectInfo{
		params.ObjectKey: {Exists: false},
		finalKey: {
			Exists: true, Sha256: objectDigest,
			ContentType: "image/jpeg", Size: 128,
		},
	}}
	completed, err := newGateway(t, retryClient, now).CompleteUpload(
		context.Background(),
		params,
	)
	if err != nil {
		t.Fatalf("retry completion from promoted CAS object: %v", err)
	}
	if completed.ObjectKey != finalKey || retryClient.promotedTo != "" {
		t.Fatalf(
			"retry must reuse verified CAS object without another promotion: result=%+v promoted=%s",
			completed,
			retryClient.promotedTo,
		)
	}
}

func TestGatewayRejectsMismatchedUploadedBytes(t *testing.T) {
	client := &objectClientStub{info: &runtimemedia.ObjectInfo{
		Exists:      true,
		Sha256:      "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
		ContentType: "image/jpeg",
		Size:        128,
	}}
	gateway := newGateway(t, client, time.Now().UTC())
	_, err := gateway.CompleteUpload(
		context.Background(),
		sessionapp.CompleteUploadParams{
			ObjectKey: "uploads/mus-1.jpg", ExpectedSHA256: objectDigest,
			MediaType: "image", ContentType: "image/jpeg", FileSize: 128,
		},
	)
	if err == nil || client.promotedTo != "" {
		t.Fatalf(
			"digest mismatch must fail before promotion, err=%v promoted=%s",
			err,
			client.promotedTo,
		)
	}
}

func TestGatewayDeletesOnlyTemporaryUploads(t *testing.T) {
	client := &objectClientStub{}
	gateway := newGateway(t, client, time.Now().UTC())
	const temporaryKey = "uploads/owner/session-1.jpg"
	if err := gateway.DeleteTemporaryUpload(
		context.Background(),
		temporaryKey,
	); err != nil {
		t.Fatalf("delete temporary upload: %v", err)
	}
	if client.deletedKey != temporaryKey {
		t.Fatalf("temporary upload deletion used wrong key: %q", client.deletedKey)
	}
	if err := gateway.DeleteTemporaryUpload(
		context.Background(),
		"media/objects/sha256/aa/aa/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.jpg",
	); err == nil {
		t.Fatal("canonical CAS objects must never use temporary cleanup")
	}
}

func newGateway(
	t *testing.T,
	client *objectClientStub,
	now time.Time,
) *Gateway {
	t.Helper()
	gateway, err := NewGateway(
		Config{
			Bucket: "media",
		},
		client,
	)
	if err != nil {
		t.Fatalf("new gateway: %v", err)
	}
	gateway.SetClock(func() time.Time { return now })
	return gateway
}

type objectClientStub struct {
	info              *runtimemedia.ObjectInfo
	infoByKey         map[string]*runtimemedia.ObjectInfo
	promotedTo        string
	promotionMetadata map[string]string
	deletedKey        string
}

func (s *objectClientStub) PresignPutObject(
	_ context.Context,
	_ string,
	key string,
	_ runtimemedia.PutObjectConstraints,
	_ time.Duration,
) (string, error) {
	return "https://upload.example.test/" + key, nil
}

func (s *objectClientStub) StatObject(
	_ context.Context,
	_ string,
	key string,
) (*runtimemedia.ObjectInfo, error) {
	if s.infoByKey != nil {
		return s.infoByKey[key], nil
	}
	return s.info, nil
}

func (s *objectClientStub) PromoteObject(
	_ context.Context,
	_ string,
	_ string,
	target string,
	metadata map[string]string,
) error {
	s.promotedTo = target
	s.promotionMetadata = metadata
	return nil
}

func (*objectClientStub) CopyObject(
	context.Context,
	string,
	string,
	string,
) error {
	return nil
}

func (s *objectClientStub) DeleteObject(
	_ context.Context,
	_ string,
	key string,
) error {
	s.deletedKey = key
	return nil
}
