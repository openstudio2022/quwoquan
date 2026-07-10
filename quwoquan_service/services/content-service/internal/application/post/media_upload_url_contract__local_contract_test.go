package post

import (
	"context"
	"strings"
	"testing"
	"time"

	runtimemedia "quwoquan_service/runtime/media"
	"quwoquan_service/services/content-service/internal/infrastructure/persistence"
)

type fakeContentMediaStore struct {
	session *runtimemedia.UploadSession
}

func (f *fakeContentMediaStore) InitUpload(_ context.Context, opts runtimemedia.InitUploadOpts) (*runtimemedia.UploadSession, error) {
	f.session = &runtimemedia.UploadSession{
		SessionID:       "store_session_1",
		Category:        opts.Category,
		OwnerID:         opts.OwnerID,
		FileName:        opts.FileName,
		ContentType:     opts.ContentType,
		FileSize:        opts.FileSize,
		PresignURL:      "https://upload.media.example.com/presigned/store-session",
		OSSKey:          "uploads/post/2026/06/04/user_42/store_session_1_original.jpg",
		TemporaryOSSKey: "uploads/post/2026/06/04/user_42/store_session_1_original.jpg",
		Status:          "pending",
		CreatedAt:       time.Now().UTC(),
		ExpiresAt:       time.Now().UTC().Add(time.Minute),
	}
	return f.session, nil
}

func (f *fakeContentMediaStore) CompleteUpload(_ context.Context, sessionID string, _ runtimemedia.CompleteUploadOpts) (*runtimemedia.MediaAsset, error) {
	return &runtimemedia.MediaAsset{
		AssetID:         "store_asset_1",
		SessionID:       sessionID,
		OwnerID:         "user_42",
		TemporaryOSSKey: "uploads/post/2026/06/04/user_42/store_session_1_original.jpg",
		OSSKey:          "media/objects/sha256/aa/bb/" + strings.Repeat("c", 64) + ".jpg",
		CDNURL:          "https://cdn.media.example.com/media/objects/sha256/aa/bb/" + strings.Repeat("c", 64) + ".jpg",
		Sha256:          "sha256:" + strings.Repeat("c", 64),
		FileSize:        2048,
		CreatedAt:       time.Now().UTC(),
	}, nil
}

func (f *fakeContentMediaStore) AbortUpload(context.Context, string) error { return nil }

func (f *fakeContentMediaStore) GetAsset(context.Context, string) (*runtimemedia.MediaAsset, error) {
	return nil, nil
}

func (f *fakeContentMediaStore) SignURL(context.Context, string, time.Duration) (string, error) {
	return "", nil
}

func TestMediaUploadUsesUnifiedObjectKeyAndCDNURL(t *testing.T) {
	svc := NewPostService(
		persistence.NewPostStore(nil),
	)

	init := svc.InitMediaUpload(context.Background(), "user_42", "image", "draft", "user_upload")
	mediaID, _ := init["mediaId"].(string)
	sessionID, _ := init["sessionId"].(string)
	objectKey, _ := init["objectKey"].(string)
	uploadURL, _ := init["uploadUrl"].(string)

	if mediaID == "" || sessionID == "" {
		t.Fatalf("init upload must return media/session ids: %+v", init)
	}
	if !strings.HasPrefix(objectKey, "uploads/post/") {
		t.Fatalf("temporary objectKey must use uploads namespace, got %q", objectKey)
	}
	if !strings.HasPrefix(uploadURL, "https://mock-oss.example.com/uploads/post/") {
		t.Fatalf("uploadUrl must use temporary uploads namespace, got %q", uploadURL)
	}

	asset, err := svc.CompleteMediaUpload(context.Background(), sessionID)
	if err != nil {
		t.Fatal(err)
	}
	if asset.ObjectKey == objectKey {
		t.Fatalf("complete must promote temporary key to final CAS key: %q", asset.ObjectKey)
	}
	if !strings.HasPrefix(asset.CdnUrl, "https://mock-cdn.example.com/media/objects/sha256/") {
		t.Fatalf("cdnUrl must be derived from configured CDN and objectKey, got %q", asset.CdnUrl)
	}
	if !strings.HasPrefix(asset.Sha256, "sha256:") || len(asset.Sha256) != len("sha256:")+64 {
		t.Fatalf("sha256 must be full digest, got %q", asset.Sha256)
	}
	if !strings.HasPrefix(asset.OriginUrl, "https://mock-cdn.example.com/media/objects/sha256/") {
		t.Fatalf("originUrl must be promoted to final CAS asset url, got %+v", asset)
	}
}

func TestMediaUploadCanUseRuntimeMediaStore(t *testing.T) {
	mediaStore := &fakeContentMediaStore{}
	svc := NewPostService(
		persistence.NewPostStore(nil),
		WithMediaStore(mediaStore),
	)

	init := svc.InitMediaUpload(context.Background(), "user_42", "image", "draft", "user_upload")
	sessionID, _ := init["sessionId"].(string)
	objectKey, _ := init["objectKey"].(string)
	uploadURL, _ := init["uploadUrl"].(string)

	if sessionID != "store_session_1" {
		t.Fatalf("expected runtime media session id, got %+v", init)
	}
	if objectKey != "uploads/post/2026/06/04/user_42/store_session_1_original.jpg" {
		t.Fatalf("expected runtime media temporary object key, got %q", objectKey)
	}
	if uploadURL != "https://upload.media.example.com/presigned/store-session" {
		t.Fatalf("expected runtime media presign URL, got %q", uploadURL)
	}

	asset, err := svc.CompleteMediaUpload(context.Background(), sessionID)
	if err != nil {
		t.Fatal(err)
	}
	if asset.CdnUrl != "https://cdn.media.example.com/media/objects/sha256/aa/bb/"+strings.Repeat("c", 64)+".jpg" {
		t.Fatalf("expected runtime media CDN URL, got %q", asset.CdnUrl)
	}
	if asset.ObjectKey == objectKey {
		t.Fatalf("expected runtime media object key to promote from temporary to CAS key, got %q", asset.ObjectKey)
	}
	if asset.Sha256 != "sha256:"+strings.Repeat("c", 64) {
		t.Fatalf("expected runtime media sha256, got %q", asset.Sha256)
	}
}
