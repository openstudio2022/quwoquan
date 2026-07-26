package media_test

import (
	"context"
	. "quwoquan_service/services/content-service/internal/content/post/infrastructure/content/media"
	"strings"
	"testing"
	"time"

	runtimemedia "quwoquan_service/runtime/media"
)

func TestObjectGatewayDeliveryURLUsesPublicSliceWithoutCASPath(t *testing.T) {
	now := time.Date(2030, time.January, 1, 0, 0, 0, 0, time.UTC)
	gateway, err := NewObjectGateway(ObjectGatewayConfig{
		Bucket: "media", CDNDomain: "https://cdn.example.test", CDNSignKey: "test-sign-key", DeliveryTTL: time.Minute,
	}, &objectClientStub{})
	if err != nil {
		t.Fatalf("new gateway: %v", err)
	}
	gateway.SetClock(func() time.Time { return now })
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

func TestObjectGatewayReclaimsOnlyValidatedClosedAccountArtifacts(t *testing.T) {
	client := &objectClientStub{}
	gateway, err := NewObjectGateway(ObjectGatewayConfig{
		Bucket: "media", CDNDomain: "cdn.example.test", CDNSignKey: "test-sign-key", DeliveryTTL: time.Minute,
	}, client)
	if err != nil {
		t.Fatalf("new gateway: %v", err)
	}
	publicKey := "media/image/s/asset/mas_image_001/v1/source.jpg"
	publicPrefix := "media/video/s/asset/mas_video_001/"
	privateKey := "media/objects/sha256/aa/aa/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.jpg"
	privatePrefix := "media/processed/image/mas_image_001/"
	if err := gateway.ReclaimMediaArtifacts(
		context.Background(),
		[]string{publicKey},
		[]string{publicPrefix},
		[]string{privateKey},
		[]string{privatePrefix},
	); err != nil {
		t.Fatalf("reclaim closed-account artifacts: %v", err)
	}
	for _, key := range []string{publicKey, privateKey} {
		if !containsObjectKey(client.deletedKeys, key) {
			t.Fatalf("artifact %q was not deleted: %v", key, client.deletedKeys)
		}
	}
	for _, prefix := range []string{publicPrefix, privatePrefix} {
		if !containsObjectKey(client.deletedPrefixes, strings.TrimSuffix(prefix, "/")) {
			t.Fatalf("artifact prefix %q was not deleted: %v", prefix, client.deletedPrefixes)
		}
	}
	if err := gateway.ReclaimMediaArtifacts(
		context.Background(),
		[]string{"uploads/not-a-public-slice"},
		nil,
		nil,
		nil,
	); err == nil {
		t.Fatal("account cleanup must reject a non-public delivery key")
	}
	if err := gateway.ReclaimMediaArtifacts(
		context.Background(),
		nil,
		nil,
		nil,
		[]string{"media/objects/sha256/"},
	); err == nil {
		t.Fatal("account cleanup must reject a shared CAS prefix")
	}
}

func TestObjectGatewayBlocksCompletionWhenArtifactReadBackFindsResiduals(
	t *testing.T,
) {
	t.Run("exact object", func(t *testing.T) {
		client := &objectClientStub{
			info: &runtimemedia.ObjectInfo{Exists: true},
		}
		gateway, err := NewObjectGateway(ObjectGatewayConfig{
			Bucket: "media", CDNDomain: "cdn.example.test",
			CDNSignKey: "test-sign-key", DeliveryTTL: time.Minute,
		}, client)
		if err != nil {
			t.Fatalf("new gateway: %v", err)
		}
		err = gateway.ReclaimMediaArtifacts(
			context.Background(),
			[]string{"media/image/s/asset/mas_image_residual/v1/source.jpg"},
			nil,
			nil,
			nil,
		)
		if err == nil || !strings.Contains(err.Error(), "still exists") {
			t.Fatalf("exact artifact residual was accepted: %v", err)
		}
	})

	t.Run("prefix", func(t *testing.T) {
		client := &objectClientStub{prefixRemaining: true}
		gateway, err := NewObjectGateway(ObjectGatewayConfig{
			Bucket: "media", CDNDomain: "cdn.example.test",
			CDNSignKey: "test-sign-key", DeliveryTTL: time.Minute,
		}, client)
		if err != nil {
			t.Fatalf("new gateway: %v", err)
		}
		err = gateway.ReclaimMediaArtifacts(
			context.Background(),
			nil,
			[]string{"media/video/s/asset/mas_video_residual/"},
			nil,
			nil,
		)
		if err == nil || !strings.Contains(err.Error(), "still contains") {
			t.Fatalf("prefix artifact residual was accepted: %v", err)
		}
	})
}

func containsObjectKey(values []string, target string) bool {
	for _, value := range values {
		if value == target {
			return true
		}
	}
	return false
}

type objectClientStub struct {
	info            *runtimemedia.ObjectInfo
	promotedTo      string
	copiedFrom      string
	copiedTo        string
	deletedKey      string
	deletedKeys     []string
	deletedPrefixes []string
	prefixRemaining bool
}

func (s *objectClientStub) PresignPutObject(_ context.Context, _ string, key string, _ runtimemedia.PutObjectConstraints, _ time.Duration) (string, error) {
	return "https://upload.example.test/" + key, nil
}

func (s *objectClientStub) StatObject(context.Context, string, string) (*runtimemedia.ObjectInfo, error) {
	if s.info == nil {
		return &runtimemedia.ObjectInfo{Exists: false}, nil
	}
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
	s.deletedKeys = append(s.deletedKeys, key)
	return nil
}

func (s *objectClientStub) DeletePrefix(
	_ context.Context,
	_ string,
	prefix string,
) error {
	s.deletedPrefixes = append(s.deletedPrefixes, prefix)
	return nil
}

func (s *objectClientStub) HasObjectsWithPrefix(
	context.Context,
	string,
	string,
) (bool, error) {
	return s.prefixRemaining, nil
}
