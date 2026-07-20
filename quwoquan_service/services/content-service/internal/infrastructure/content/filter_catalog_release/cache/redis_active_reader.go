package cache

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"log/slog"
	"time"

	rtredis "quwoquan_service/runtime/redis"
	"quwoquan_service/services/content-service/internal/domain/content/filter_catalog_release/model"
	filtercatalogports "quwoquan_service/services/content-service/internal/domain/content/filter_catalog_release/ports"
)

const (
	activeFilterCatalogCacheKey = "content:filter-catalog:active"
	activeFilterCatalogCacheTTL = 6 * time.Hour
)

type ActiveReader struct {
	source filtercatalogports.ActiveFilterCatalogReader
	client rtredis.Client
	logger *slog.Logger
}

type activeFilterCatalogCacheDocument struct {
	ReleaseID                    string                           `json:"releaseId"`
	Version                      int64                            `json:"version"`
	SourceOwner                  string                           `json:"sourceOwner"`
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

func NewActiveReader(
	source filtercatalogports.ActiveFilterCatalogReader,
	client rtredis.Client,
	logger *slog.Logger,
) *ActiveReader {
	if source == nil {
		panic("ActiveFilterCatalogReader source is required")
	}
	if client == nil {
		panic("FilterCatalogRelease Redis client is required")
	}
	return &ActiveReader{source: source, client: client, logger: logger}
}

func (reader *ActiveReader) GetActive(
	ctx context.Context,
) (*model.FilterCatalogRelease, bool, error) {
	encoded, err := reader.client.GetBytes(ctx, activeFilterCatalogCacheKey)
	switch {
	case err == nil:
		release, decodeErr := decodeActiveFilterCatalog(encoded)
		if decodeErr == nil {
			return release, true, nil
		}
		reader.warn("filter catalog cache decode failed", decodeErr)
		if deleteErr := reader.client.Del(ctx, activeFilterCatalogCacheKey); deleteErr != nil {
			reader.warn("filter catalog invalid cache delete failed", deleteErr)
		}
	case errors.Is(err, rtredis.ErrKeyNotFound):
	default:
		reader.warn("filter catalog cache read failed", err)
	}

	release, found, err := reader.source.GetActive(ctx)
	if err != nil || !found {
		return release, found, err
	}
	encoded, err = encodeActiveFilterCatalog(release)
	if err != nil {
		return nil, false, err
	}
	if cacheErr := reader.client.SetBytes(
		ctx,
		activeFilterCatalogCacheKey,
		encoded,
		activeFilterCatalogCacheTTL,
	); cacheErr != nil {
		reader.warn("filter catalog cache write failed", cacheErr)
	}
	return release, true, nil
}

func (reader *ActiveReader) InvalidateActive(ctx context.Context) error {
	return reader.client.Del(ctx, activeFilterCatalogCacheKey)
}

func (reader *ActiveReader) warn(message string, err error) {
	if reader.logger != nil {
		reader.logger.Warn(message, "error", err)
	}
}

func encodeActiveFilterCatalog(
	release *model.FilterCatalogRelease,
) ([]byte, error) {
	snapshot := release.Snapshot()
	return json.Marshal(activeFilterCatalogCacheDocument{
		ReleaseID:                    snapshot.ReleaseID,
		Version:                      snapshot.Version,
		SourceOwner:                  snapshot.SourceOwner,
		CanonicalDigest:              snapshot.CanonicalDigest,
		Status:                       snapshot.Status,
		CategoryCount:                snapshot.CategoryCount,
		PresetCount:                  snapshot.PresetCount,
		Categories:                   snapshot.Categories,
		Presets:                      snapshot.Presets,
		RecommendedFallbackPresetIDs: snapshot.RecommendedFallbackPresetIDs,
		ImportedAt:                   snapshot.ImportedAt,
		ActivatedAt:                  snapshot.ActivatedAt,
	})
}

func decodeActiveFilterCatalog(
	encoded []byte,
) (*model.FilterCatalogRelease, error) {
	var document activeFilterCatalogCacheDocument
	if err := json.Unmarshal(encoded, &document); err != nil {
		return nil, err
	}
	if document.Status != model.StatusActive {
		return nil, fmt.Errorf("cached FilterCatalogRelease is %q", document.Status)
	}
	return model.Restore(model.Snapshot{
		ReleaseID:                    document.ReleaseID,
		Version:                      document.Version,
		SourceOwner:                  document.SourceOwner,
		CanonicalDigest:              document.CanonicalDigest,
		Status:                       document.Status,
		CategoryCount:                document.CategoryCount,
		PresetCount:                  document.PresetCount,
		Categories:                   document.Categories,
		Presets:                      document.Presets,
		RecommendedFallbackPresetIDs: document.RecommendedFallbackPresetIDs,
		ImportedAt:                   document.ImportedAt,
		ActivatedAt:                  document.ActivatedAt,
	})
}

var _ filtercatalogports.ActiveFilterCatalogReader = (*ActiveReader)(nil)
var _ filtercatalogports.ActiveFilterCatalogInvalidator = (*ActiveReader)(nil)
