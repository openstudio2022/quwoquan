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

type objectClientStub struct {
	info       *runtimemedia.ObjectInfo
	promotedTo string
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
