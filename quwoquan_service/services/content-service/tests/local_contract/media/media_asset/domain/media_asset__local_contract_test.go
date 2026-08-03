package domain_test

import (
	"errors"
	"testing"
	"time"

	mediamodel "quwoquan_service/services/content-service/internal/media/media_asset/domain/model"
)

func TestMediaAssetOwnsIdentityLifecycleAndOwnerInvariant(t *testing.T) {
	now := time.Date(2030, time.May, 6, 7, 8, 9, 0, time.UTC)
	asset, err := mediamodel.CreateMediaAsset(mediamodel.CreateMediaAssetParams{
		ID: "media-file", OwnerID: "persona-owner", SourceSessionID: "upload-file",
		ObjectKey: "media/original/file.pdf",
		SHA256:    "sha256:dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd",
		MediaType: mediamodel.MediaTypeFile, MimeType: "application/pdf", FileSize: 1024,
		AccessPolicy: mediamodel.AccessPolicyOwnerOnly, ProcessingRequired: false, Now: now,
	})
	if err != nil {
		t.Fatalf("create MediaAsset: %v", err)
	}
	if asset.ID() != "media-file" || asset.Version() != 1 || asset.ProcessingStatus() != mediamodel.ProcessingStatusReady {
		t.Fatalf("unexpected initial aggregate: %+v", asset.Snapshot())
	}
	if err := asset.ChangeAccessPolicy(
		"another-persona",
		mediamodel.AccessPolicyPublic,
		now.Add(time.Second),
	); !errors.Is(err, mediamodel.ErrMediaAssetOwnerForbidden) {
		t.Fatalf("non-owner policy mutation error=%v", err)
	}
	if err := asset.ChangeAccessPolicy(
		"persona-owner",
		mediamodel.AccessPolicyPublic,
		now.Add(time.Second),
	); err != nil {
		t.Fatalf("owner policy mutation: %v", err)
	}
	if asset.Version() != 2 || asset.AccessPolicy() != mediamodel.AccessPolicyPublic {
		t.Fatalf("policy mutation did not advance canonical aggregate: %+v", asset.Snapshot())
	}
}
