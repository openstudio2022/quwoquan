package runtimemedia

import (
	"context"
	"testing"
)

func TestMockMediaStore_InitUpload(t *testing.T) {
	store := NewMockMediaStore()
	ctx := context.Background()

	session, err := store.InitUpload(ctx, InitUploadOpts{
		Category:    CategoryChatVoice,
		OwnerID:     "user_001",
		FileName:    "voice.m4a",
		ContentType: "audio/mp4",
		FileSize:    48000,
	})

	if err != nil {
		t.Fatalf("InitUpload failed: %v", err)
	}
	if session.SessionID == "" {
		t.Error("expected non-empty session ID")
	}
	if session.Status != "pending" {
		t.Errorf("expected status=pending, got %s", session.Status)
	}
	if session.PresignURL == "" {
		t.Error("expected non-empty presign URL")
	}
	if store.SessionCount() != 1 {
		t.Errorf("expected 1 session, got %d", store.SessionCount())
	}
}

func TestMockMediaStore_CompleteUpload(t *testing.T) {
	store := NewMockMediaStore()
	ctx := context.Background()

	session, _ := store.InitUpload(ctx, InitUploadOpts{
		Category:    CategoryChatVoice,
		OwnerID:     "user_001",
		FileName:    "voice.m4a",
		ContentType: "audio/mp4",
		FileSize:    48000,
	})

	asset, err := store.CompleteUpload(ctx, session.SessionID, CompleteUploadOpts{
		DurationMs: 5200,
	})

	if err != nil {
		t.Fatalf("CompleteUpload failed: %v", err)
	}
	if asset.AssetID == "" {
		t.Error("expected non-empty asset ID")
	}
	if asset.CDNURL == "" {
		t.Error("expected non-empty CDN URL")
	}
	if asset.DurationMs != 5200 {
		t.Errorf("expected durationMs=5200, got %d", asset.DurationMs)
	}
	if store.AssetCount() != 1 {
		t.Errorf("expected 1 asset, got %d", store.AssetCount())
	}
}

func TestMockMediaStore_AbortUpload(t *testing.T) {
	store := NewMockMediaStore()
	ctx := context.Background()

	session, _ := store.InitUpload(ctx, InitUploadOpts{
		Category:    CategoryChatVoice,
		OwnerID:     "user_001",
		FileName:    "voice.m4a",
		ContentType: "audio/mp4",
		FileSize:    48000,
	})

	err := store.AbortUpload(ctx, session.SessionID)
	if err != nil {
		t.Fatalf("AbortUpload failed: %v", err)
	}

	_, err = store.CompleteUpload(ctx, session.SessionID, CompleteUploadOpts{})
	if err == nil {
		t.Error("expected error completing aborted session")
	}
}

func TestMockMediaStore_GetAsset(t *testing.T) {
	store := NewMockMediaStore()
	ctx := context.Background()

	session, _ := store.InitUpload(ctx, InitUploadOpts{
		Category:    CategoryPost,
		OwnerID:     "user_002",
		FileName:    "photo.jpg",
		ContentType: "image/jpeg",
		FileSize:    1024000,
	})
	asset, _ := store.CompleteUpload(ctx, session.SessionID, CompleteUploadOpts{
		Width:  1920,
		Height: 1080,
	})

	retrieved, err := store.GetAsset(ctx, asset.AssetID)
	if err != nil {
		t.Fatalf("GetAsset failed: %v", err)
	}
	if retrieved.Width != 1920 {
		t.Errorf("expected width=1920, got %d", retrieved.Width)
	}
}

func TestMockMediaStore_GetAsset_NotFound(t *testing.T) {
	store := NewMockMediaStore()
	ctx := context.Background()

	_, err := store.GetAsset(ctx, "nonexistent")
	if err == nil {
		t.Error("expected error for nonexistent asset")
	}
}

func TestValidateUpload_ChatVoice_ValidAAC(t *testing.T) {
	err := ValidateUpload(InitUploadOpts{
		Category:    CategoryChatVoice,
		FileSize:    48000,
		ContentType: "audio/mp4",
	})
	if err != nil {
		t.Errorf("expected valid upload, got error: %v", err)
	}
}

func TestValidateUpload_ChatVoice_TooLarge(t *testing.T) {
	err := ValidateUpload(InitUploadOpts{
		Category:    CategoryChatVoice,
		FileSize:    20 * 1024 * 1024,
		ContentType: "audio/mp4",
	})
	if err == nil {
		t.Error("expected error for oversized file")
	}
}

func TestValidateUpload_ChatVoice_WrongType(t *testing.T) {
	err := ValidateUpload(InitUploadOpts{
		Category:    CategoryChatVoice,
		FileSize:    48000,
		ContentType: "video/mp4",
	})
	if err == nil {
		t.Error("expected error for wrong content type")
	}
}

func TestValidateUpload_UnknownCategory(t *testing.T) {
	err := ValidateUpload(InitUploadOpts{
		Category:    MediaCategory("unknown"),
		FileSize:    1000,
		ContentType: "application/octet-stream",
	})
	if err == nil {
		t.Error("expected error for unknown category")
	}
}

func TestMockMediaStore_SignURL(t *testing.T) {
	store := NewMockMediaStore()
	ctx := context.Background()

	url, err := store.SignURL(ctx, "media/chat_voice/test.m4a", 0)
	if err != nil {
		t.Fatalf("SignURL failed: %v", err)
	}
	if url == "" {
		t.Error("expected non-empty signed URL")
	}
}

func TestMockMediaStore_Reset(t *testing.T) {
	store := NewMockMediaStore()
	ctx := context.Background()

	store.InitUpload(ctx, InitUploadOpts{
		Category:    CategoryChatVoice,
		OwnerID:     "u",
		FileName:    "v.m4a",
		ContentType: "audio/mp4",
		FileSize:    100,
	})

	store.Reset()
	if store.SessionCount() != 0 {
		t.Error("expected 0 sessions after reset")
	}
	if store.AssetCount() != 0 {
		t.Error("expected 0 assets after reset")
	}
}
