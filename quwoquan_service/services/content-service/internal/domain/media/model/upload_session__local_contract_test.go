package model

import (
	"strings"
	"testing"
	"time"
)

func TestCompletedUploadSessionPersistsCreatedAssetIdentity(t *testing.T) {
	now := time.Date(2026, 7, 20, 12, 0, 0, 0, time.UTC)
	session, err := CreateUploadSession(CreateUploadSessionParams{
		ID:             "mus_1",
		OwnerID:        "persona-1",
		ObjectKey:      "media/private/object",
		MediaType:      "video",
		ContentType:    "video/mp4",
		FileSize:       4,
		ExpectedSHA256: strings.Repeat("a", 64),
		ExpiresAt:      now.Add(15 * time.Minute),
		Now:            now,
	})
	if err != nil {
		t.Fatalf("create upload session: %v", err)
	}

	if err := session.Complete(
		"persona-1",
		strings.Repeat("a", 64),
		"mas_1",
		now.Add(time.Minute),
	); err != nil {
		t.Fatalf("complete upload session: %v", err)
	}
	if session.AssetID() != "mas_1" {
		t.Fatalf("asset id=%q want mas_1", session.AssetID())
	}
	restored, err := RestoreUploadSession(session.Snapshot())
	if err != nil {
		t.Fatalf("restore completed upload session: %v", err)
	}
	if restored.AssetID() != "mas_1" ||
		restored.Status() != UploadSessionCompleted {
		t.Fatalf("completed session identity did not survive restore: %#v", restored.Snapshot())
	}
}

func TestCompletedUploadSessionRejectsMissingAssetIdentity(t *testing.T) {
	now := time.Date(2026, 7, 20, 12, 0, 0, 0, time.UTC)
	_, err := RestoreUploadSession(UploadSessionSnapshot{
		ID:             "mus_invalid",
		Version:        2,
		OwnerID:        "persona-1",
		ObjectKey:      "media/private/object",
		MediaType:      "image",
		ContentType:    "image/jpeg",
		FileSize:       4,
		ExpectedSHA256: strings.Repeat("a", 64),
		Status:         UploadSessionCompleted,
		CreatedAt:      now,
		UpdatedAt:      now.Add(time.Minute),
		ExpiresAt:      now.Add(15 * time.Minute),
		CompletedAt:    pointerTime(now.Add(time.Minute)),
	})
	if err == nil {
		t.Fatal("expected completed session without asset identity to be rejected")
	}
}

func pointerTime(value time.Time) *time.Time {
	return &value
}
