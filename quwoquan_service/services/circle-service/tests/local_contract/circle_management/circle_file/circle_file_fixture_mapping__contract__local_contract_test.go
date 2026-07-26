package local_contract

import (
	"testing"

	seedfixture "quwoquan_service/services/circle-service/internal/circle_management/circle_file/infrastructure/seedfixture"
)

func TestCircleFileFixtureMappingUsesCurrentMediaAssetContract(t *testing.T) {
	fixture := seedfixture.CircleFile{
		ID: "file-1", Version: 3, CircleID: "circle-1", GroupID: "group-1",
		ParentFolderID: "folder-1", Name: "guide.png", FileType: "file",
		AssetID: "asset-1", MimeType: "image/png", SizeBytes: 4096,
		UploaderPersonaID: "persona-1", Status: "active",
		CreatedAt: "2026-07-15T00:00:00Z", UpdatedAt: "2026-07-15T00:01:00Z",
	}
	file := seedfixture.CircleFileFromFixture(fixture)
	if file.Version != fixture.Version || file.AssetID != fixture.AssetID ||
		file.UploaderPersonaID != fixture.UploaderPersonaID || file.ParentFolderID != fixture.ParentFolderID {
		t.Fatalf("fixture mapping lost canonical CircleFile fields: %#v", file)
	}
	if file.CreatedAt.IsZero() || file.UpdatedAt.IsZero() {
		t.Fatalf("fixture timestamps must be parsed: %#v", file)
	}
}

func TestContentFixtureSeedsActiveCirclePostPlacement(t *testing.T) {
	post := seedfixture.ContentPost{
		PostID: "fixture_post_tech_001", CircleIDs: []string{"fixture_circle_tech_01"},
		CreatedAt: "2026-07-21T00:00:00Z", UpdatedAt: "2026-07-21T00:01:00Z",
	}
	placementID, placement := seedfixture.CirclePlacementDocFromFixture(post, "fixture_circle_tech_01")
	if placementID != "fixture_placement_fixture_circle_tech_01_fixture_post_tech_001" {
		t.Fatalf("unexpected deterministic placement id %q", placementID)
	}
	if placement["circleId"] != "fixture_circle_tech_01" ||
		placement["postId"] != "fixture_post_tech_001" || placement["state"] != "active" {
		t.Fatalf("fixture placement must be feed-readable: %#v", placement)
	}
}
