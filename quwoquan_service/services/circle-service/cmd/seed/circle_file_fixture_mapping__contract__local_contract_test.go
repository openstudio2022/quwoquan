package main

import "testing"

func TestCircleFileFixtureMappingUsesCurrentMediaAssetContract(t *testing.T) {
	fixture := circleFixtureFile{
		ID:                "file-1",
		Version:           3,
		CircleID:          "circle-1",
		GroupID:           "group-1",
		ParentFolderID:    "folder-1",
		Name:              "guide.png",
		FileType:          "file",
		AssetID:           "asset-1",
		MimeType:          "image/png",
		SizeBytes:         4096,
		UploaderPersonaID: "persona-1",
		Status:            "active",
		CreatedAt:         "2026-07-15T00:00:00Z",
		UpdatedAt:         "2026-07-15T00:01:00Z",
	}

	file := circleFileFromFixture(fixture)
	if file.Version != fixture.Version || file.AssetID != fixture.AssetID ||
		file.UploaderPersonaID != fixture.UploaderPersonaID || file.ParentFolderID != fixture.ParentFolderID {
		t.Fatalf("fixture mapping lost canonical CircleFile fields: %#v", file)
	}
	if file.CreatedAt.IsZero() || file.UpdatedAt.IsZero() {
		t.Fatalf("fixture timestamps must be parsed: %#v", file)
	}
}
