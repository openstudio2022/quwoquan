package filtercatalogrelease

import (
	"context"
	"time"

	"quwoquan_service/services/content-service/internal/domain/content/filter_catalog_release/model"
)

type StageFilterCatalogReleaseCommand struct {
	ReleaseID                    string
	SourceOwner                  string
	CanonicalDigest              string
	Categories                   []model.FilterCategoryDefinition
	Presets                      []model.FilterPresetDefinition
	RecommendedFallbackPresetIDs []string
}

type ActivateFilterCatalogReleaseCommand struct {
	ReleaseID string
}

type RollbackFilterCatalogReleaseCommand struct {
	ReleaseID string
}

type FilterCatalogReleaseCommandResult struct {
	Release  FilterCatalogSlice
	Changed  bool
	Replayed bool
}

// FilterCatalogSlice 是 GetActiveFilterCatalog 的公开强类型投影。
// sourceOwner、version 与 receipt 永远不进入该 Slice。
type FilterCatalogSlice struct {
	ReleaseID                    string                           `json:"releaseId"`
	CanonicalDigest              string                           `json:"canonicalDigest"`
	Status                       model.Status                     `json:"status"`
	CategoryCount                int                              `json:"categoryCount"`
	PresetCount                  int                              `json:"presetCount"`
	Categories                   []model.FilterCategoryDefinition `json:"categories"`
	Presets                      []model.FilterPresetDefinition   `json:"presets"`
	RecommendedFallbackPresetIDs []string                         `json:"recommendedFallbackPresetIds"`
	ImportedAt                   time.Time                        `json:"importedAt"`
	ActivatedAt                  *time.Time                       `json:"activatedAt"`
}

type FilterCatalogReleaseCommandFacet interface {
	Stage(
		ctx context.Context,
		command StageFilterCatalogReleaseCommand,
	) (FilterCatalogReleaseCommandResult, error)
	Activate(
		ctx context.Context,
		command ActivateFilterCatalogReleaseCommand,
	) (FilterCatalogReleaseCommandResult, error)
	Rollback(
		ctx context.Context,
		command RollbackFilterCatalogReleaseCommand,
	) (FilterCatalogReleaseCommandResult, error)
}

type FilterCatalogQueryFacet interface {
	GetActiveFilterCatalog(ctx context.Context) (FilterCatalogSlice, error)
}

func filterCatalogSlice(release *model.FilterCatalogRelease) FilterCatalogSlice {
	snapshot := release.Snapshot()
	return FilterCatalogSlice{
		ReleaseID:                    snapshot.ReleaseID,
		CanonicalDigest:              snapshot.CanonicalDigest,
		Status:                       snapshot.Status,
		CategoryCount:                snapshot.CategoryCount,
		PresetCount:                  snapshot.PresetCount,
		Categories:                   snapshot.Categories,
		Presets:                      snapshot.Presets,
		RecommendedFallbackPresetIDs: snapshot.RecommendedFallbackPresetIDs,
		ImportedAt:                   snapshot.ImportedAt,
		ActivatedAt:                  snapshot.ActivatedAt,
	}
}
