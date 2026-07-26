package local_contract

import (
	"errors"
	. "quwoquan_service/services/circle-service/internal/circle_management/circle_file/domain/model"
	"testing"
	"time"
)

func TestApplyCreateRequiresReadyAssetSnapshotForFile(t *testing.T) {
	name := "guide.pdf"
	_, err := Apply(nil, ChangeSet{
		Kind: ChangeCreate, FileID: "file_1", CircleID: "circle_1", Name: &name,
		FileType: CircleFileTypeFile, UploaderPersonaID: "persona_1", OccurredAt: time.Now(),
	})
	if !errors.Is(err, ErrAssetInvalid) {
		t.Fatalf("expected asset invariant, got %v", err)
	}
}

func TestApplyFolderRejectsMediaAsset(t *testing.T) {
	name := "docs"
	_, err := Apply(nil, ChangeSet{
		Kind: ChangeCreate, FileID: "folder_1", CircleID: "circle_1", Name: &name,
		FileType: CircleFileTypeFolder, AssetID: "asset_1", MimeType: "x", SizeBytes: 1,
		UploaderPersonaID: "persona_1", OccurredAt: time.Now(),
	})
	if !errors.Is(err, ErrAssetInvalid) {
		t.Fatalf("expected folder asset invariant, got %v", err)
	}
}

func TestApplyVersionAndDeletedTerminalState(t *testing.T) {
	name := "docs"
	created, err := Apply(nil, ChangeSet{
		Kind: ChangeCreate, FileID: "folder_1", CircleID: "circle_1", Name: &name,
		FileType: CircleFileTypeFolder, UploaderPersonaID: "persona_1", OccurredAt: time.Now(),
	})
	if err != nil {
		t.Fatal(err)
	}
	deleted, err := Apply(&created, ChangeSet{
		Kind: ChangeDelete, FileID: created.ID, CircleID: created.CircleID,
		ExpectedVersion: 1, OccurredAt: time.Now(),
	})
	if err != nil || deleted.Version != 2 || deleted.Status != CircleFileStatusDeleted {
		t.Fatalf("unexpected delete result: %+v, %v", deleted, err)
	}
	_, err = Apply(&deleted, ChangeSet{
		Kind: ChangeDelete, FileID: deleted.ID, ExpectedVersion: 2, OccurredAt: time.Now(),
	})
	if !errors.Is(err, ErrDeleted) {
		t.Fatalf("expected deleted terminal state, got %v", err)
	}
}
