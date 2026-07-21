package media

import (
	"context"
	"strings"
	"testing"
	"time"

	runtimemedia "quwoquan_service/runtime/media"
	mediaapp "quwoquan_service/services/content-service/internal/application/media"
)

const objectDigest = "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"

func TestObjectGatewayVerifiesObjectBeforeCASPromotion(t *testing.T) {
	now := time.Date(2030, time.January, 1, 0, 0, 0, 0, time.UTC)
	client := &objectClientStub{info: &runtimemedia.ObjectInfo{
		Exists: true, Sha256: objectDigest, ContentType: "image/jpeg", Size: 128,
	}}
	gateway, err := NewObjectGateway(ObjectGatewayConfig{
		Bucket: "media", CDNDomain: "cdn.example.test", CDNSignKey: "test-sign-key", DeliveryTTL: time.Minute,
	}, client)
	if err != nil {
		t.Fatalf("new gateway: %v", err)
	}
	gateway.now = func() time.Time { return now }
	grant, err := gateway.PrepareUpload(context.Background(), mediaapp.PrepareUploadParams{
		SessionID: "mus-1", OwnerID: "persona-1", MediaType: "image", ContentType: "image/jpeg",
		FileSize: 128, ExpectedSHA256: objectDigest, ExpiresAt: now.Add(15 * time.Minute),
	})
	if err != nil {
		t.Fatalf("prepare upload: %v", err)
	}
	if grant.UploadURL == "" || strings.Contains(grant.ObjectKey, "persona-1") {
		t.Fatalf("upload grant must be signed without leaking owner id: %+v", grant)
	}
	completed, err := gateway.CompleteUpload(context.Background(), mediaapp.CompleteUploadParams{
		ObjectKey: grant.ObjectKey, ExpectedSHA256: objectDigest, MediaType: "image", ContentType: "image/jpeg", FileSize: 128,
	})
	if err != nil {
		t.Fatalf("complete upload: %v", err)
	}
	if !strings.HasPrefix(completed.ObjectKey, "media/objects/sha256/aa/aa/") || client.promotedTo != completed.ObjectKey {
		t.Fatalf("completion must promote to canonical CAS key: result=%+v promoted=%s", completed, client.promotedTo)
	}
}

func TestObjectGatewayDeliveryURLUsesPublicSliceWithoutCASPath(t *testing.T) {
	now := time.Date(2030, time.January, 1, 0, 0, 0, 0, time.UTC)
	gateway, err := NewObjectGateway(ObjectGatewayConfig{
		Bucket: "media", CDNDomain: "https://cdn.example.test", CDNSignKey: "test-sign-key", DeliveryTTL: time.Minute,
	}, &objectClientStub{})
	if err != nil {
		t.Fatalf("new gateway: %v", err)
	}
	gateway.now = func() time.Time { return now }
	const publicSlice = "media/video/s/video-primary-0001/post/video-content-0001/source.mp4"
	delivery, err := gateway.DeliveryURL(context.Background(), publicSlice)
	if err != nil {
		t.Fatalf("delivery url: %v", err)
	}
	if delivery != "https://cdn.example.test/"+publicSlice {
		t.Fatalf("public slice delivery must be base+key without CAS path, got %q", delivery)
	}
	if strings.Contains(delivery, "media/objects/sha256/") || strings.Contains(delivery, "sign=") {
		t.Fatalf("public slice delivery must not look like signed CAS URL: %q", delivery)
	}
}

func TestObjectGatewayMaterializesPublicSliceWithoutPromotingAwayCASSource(t *testing.T) {
	client := &objectClientStub{}
	gateway, err := NewObjectGateway(ObjectGatewayConfig{
		Bucket: "media", CDNDomain: "https://cdn.example.test", CDNSignKey: "test-sign-key", DeliveryTTL: time.Minute,
	}, client)
	if err != nil {
		t.Fatalf("new gateway: %v", err)
	}
	const source = "media/objects/sha256/aa/aa/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.mp4"
	const target = "media/video/s/asset/mas_video_001/v1/source.mp4"
	if err := gateway.PublishPublicSlice(context.Background(), source, target); err != nil {
		t.Fatalf("materialize public slice: %v", err)
	}
	if client.copiedFrom != source || client.copiedTo != target {
		t.Fatalf("unexpected public copy: from=%q to=%q", client.copiedFrom, client.copiedTo)
	}
	if client.promotedTo != "" {
		t.Fatalf("public materialization must not delete/promote the CAS source: %q", client.promotedTo)
	}
}

func TestObjectGatewayRejectsMismatchedUploadedBytes(t *testing.T) {
	client := &objectClientStub{info: &runtimemedia.ObjectInfo{
		Exists: true, Sha256: "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb", ContentType: "image/jpeg", Size: 128,
	}}
	gateway, err := NewObjectGateway(ObjectGatewayConfig{
		Bucket: "media", CDNDomain: "cdn.example.test", CDNSignKey: "test-sign-key", DeliveryTTL: time.Minute,
	}, client)
	if err != nil {
		t.Fatalf("new gateway: %v", err)
	}
	_, err = gateway.CompleteUpload(context.Background(), mediaapp.CompleteUploadParams{
		ObjectKey: "uploads/mus-1.jpg", ExpectedSHA256: objectDigest, MediaType: "image", ContentType: "image/jpeg", FileSize: 128,
	})
	if err == nil || client.promotedTo != "" {
		t.Fatalf("digest mismatch must fail before promotion, err=%v promoted=%s", err, client.promotedTo)
	}
}

func TestObjectGatewayDeletesOnlyTemporaryUploads(t *testing.T) {
	client := &objectClientStub{}
	gateway, err := NewObjectGateway(ObjectGatewayConfig{
		Bucket: "media", CDNDomain: "cdn.example.test", CDNSignKey: "test-sign-key", DeliveryTTL: time.Minute,
	}, client)
	if err != nil {
		t.Fatalf("new gateway: %v", err)
	}
	const temporaryKey = "uploads/owner/session-1.jpg"
	if err := gateway.DeleteTemporaryUpload(context.Background(), temporaryKey); err != nil {
		t.Fatalf("delete temporary upload: %v", err)
	}
	if client.deletedKey != temporaryKey {
		t.Fatalf("temporary upload deletion used wrong key: %q", client.deletedKey)
	}
	if err := gateway.DeleteTemporaryUpload(
		context.Background(),
		"media/objects/sha256/aa/aa/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.jpg",
	); err == nil {
		t.Fatal("canonical CAS objects must never be deleted through temporary cleanup")
	}
}

type objectClientStub struct {
	info       *runtimemedia.ObjectInfo
	promotedTo string
	copiedFrom string
	copiedTo   string
	deletedKey string
}

func (s *objectClientStub) PresignPutObject(_ context.Context, _ string, key string, _ runtimemedia.PutObjectConstraints, _ time.Duration) (string, error) {
	return "https://upload.example.test/" + key, nil
}

func (s *objectClientStub) StatObject(context.Context, string, string) (*runtimemedia.ObjectInfo, error) {
	return s.info, nil
}

func (s *objectClientStub) PromoteObject(_ context.Context, _ string, _ string, target string, _ map[string]string) error {
	s.promotedTo = target
	return nil
}

func (s *objectClientStub) CopyObject(_ context.Context, _ string, source string, target string) error {
	s.copiedFrom = source
	s.copiedTo = target
	return nil
}

func (s *objectClientStub) DeleteObject(_ context.Context, _ string, key string) error {
	s.deletedKey = key
	return nil
}
