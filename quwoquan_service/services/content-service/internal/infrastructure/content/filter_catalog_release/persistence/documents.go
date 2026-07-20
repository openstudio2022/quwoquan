package persistence

import (
	"time"

	"quwoquan_service/services/content-service/internal/domain/content/filter_catalog_release/model"
)

type filterCatalogCategoryDocument struct {
	CategoryID        string  `bson:"categoryId"`
	DisplayNameZhHans string  `bson:"displayNameZhHans"`
	DisplayNameEn     *string `bson:"displayNameEn"`
	Sort              int     `bson:"sort"`
	Enabled           bool    `bson:"enabled"`
}

type filterCatalogAdjustmentDocument struct {
	LightSense  float64 `bson:"lightSense"`
	Brightness  float64 `bson:"brightness"`
	Exposure    float64 `bson:"exposure"`
	Contrast    float64 `bson:"contrast"`
	Saturation  float64 `bson:"saturation"`
	Vibrance    float64 `bson:"vibrance"`
	Texture     float64 `bson:"texture"`
	Sharpen     float64 `bson:"sharpen"`
	Structure   float64 `bson:"structure"`
	Highlight   float64 `bson:"highlight"`
	Shadow      float64 `bson:"shadow"`
	Temperature float64 `bson:"temperature"`
	Tint        float64 `bson:"tint"`
	Grain       float64 `bson:"grain"`
	Fade        float64 `bson:"fade"`
}

type filterCatalogPresetDocument struct {
	PresetID          string                          `bson:"presetId"`
	CategoryID        string                          `bson:"categoryId"`
	DisplayNameZhHans string                          `bson:"displayNameZhHans"`
	DisplayNameEn     *string                         `bson:"displayNameEn"`
	Sort              int                             `bson:"sort"`
	Enabled           bool                            `bson:"enabled"`
	DefaultStrength   float64                         `bson:"defaultStrength"`
	Adjustments       filterCatalogAdjustmentDocument `bson:"adjustments"`
}

type filterCatalogReleaseDocument struct {
	ID                           string                          `bson:"_id"`
	ReleaseID                    string                          `bson:"releaseId"`
	Version                      int64                           `bson:"version"`
	SourceOwner                  string                          `bson:"sourceOwner"`
	CanonicalDigest              string                          `bson:"canonicalDigest"`
	Status                       string                          `bson:"status"`
	CategoryCount                int                             `bson:"categoryCount"`
	PresetCount                  int                             `bson:"presetCount"`
	Categories                   []filterCatalogCategoryDocument `bson:"categories"`
	Presets                      []filterCatalogPresetDocument   `bson:"presets"`
	RecommendedFallbackPresetIDs []string                        `bson:"recommendedFallbackPresetIds"`
	ImportedAt                   time.Time                       `bson:"importedAt"`
	ActivatedAt                  *time.Time                      `bson:"activatedAt,omitempty"`
}

type filterCatalogReceiptDocument struct {
	ID               string                       `bson:"_id"`
	AggregateID      string                       `bson:"aggregateId"`
	AggregateVersion int64                        `bson:"aggregateVersion"`
	CommandName      string                       `bson:"commandName"`
	CommandDigest    string                       `bson:"commandDigest"`
	Result           filterCatalogReleaseDocument `bson:"result"`
	Changed          bool                         `bson:"changed"`
	CreatedAt        time.Time                    `bson:"createdAt"`
	ExpiresAt        time.Time                    `bson:"expiresAt"`
}

func filterCatalogDocumentFromRelease(
	release *model.FilterCatalogRelease,
) filterCatalogReleaseDocument {
	snapshot := release.Snapshot()
	categories := make([]filterCatalogCategoryDocument, len(snapshot.Categories))
	for index, category := range snapshot.Categories {
		categories[index] = filterCatalogCategoryDocument{
			CategoryID:        category.CategoryID,
			DisplayNameZhHans: category.DisplayNameZhHans,
			DisplayNameEn:     cloneDocumentString(category.DisplayNameEn),
			Sort:              category.Sort,
			Enabled:           category.Enabled,
		}
	}
	presets := make([]filterCatalogPresetDocument, len(snapshot.Presets))
	for index, preset := range snapshot.Presets {
		presets[index] = filterCatalogPresetDocument{
			PresetID:          preset.PresetID,
			CategoryID:        preset.CategoryID,
			DisplayNameZhHans: preset.DisplayNameZhHans,
			DisplayNameEn:     cloneDocumentString(preset.DisplayNameEn),
			Sort:              preset.Sort,
			Enabled:           preset.Enabled,
			DefaultStrength:   preset.DefaultStrength,
			Adjustments:       filterCatalogAdjustmentDocumentFromModel(preset.Adjustments),
		}
	}
	return filterCatalogReleaseDocument{
		ID:                           snapshot.ReleaseID,
		ReleaseID:                    snapshot.ReleaseID,
		Version:                      snapshot.Version,
		SourceOwner:                  snapshot.SourceOwner,
		CanonicalDigest:              snapshot.CanonicalDigest,
		Status:                       string(snapshot.Status),
		CategoryCount:                snapshot.CategoryCount,
		PresetCount:                  snapshot.PresetCount,
		Categories:                   categories,
		Presets:                      presets,
		RecommendedFallbackPresetIDs: cloneDocumentStrings(snapshot.RecommendedFallbackPresetIDs),
		ImportedAt:                   snapshot.ImportedAt,
		ActivatedAt:                  cloneDocumentTime(snapshot.ActivatedAt),
	}
}

func (document filterCatalogReleaseDocument) release() (*model.FilterCatalogRelease, error) {
	categories := make([]model.FilterCategoryDefinition, len(document.Categories))
	for index, category := range document.Categories {
		categories[index] = model.FilterCategoryDefinition{
			CategoryID:        category.CategoryID,
			DisplayNameZhHans: category.DisplayNameZhHans,
			DisplayNameEn:     cloneDocumentString(category.DisplayNameEn),
			Sort:              category.Sort,
			Enabled:           category.Enabled,
		}
	}
	presets := make([]model.FilterPresetDefinition, len(document.Presets))
	for index, preset := range document.Presets {
		presets[index] = model.FilterPresetDefinition{
			PresetID:          preset.PresetID,
			CategoryID:        preset.CategoryID,
			DisplayNameZhHans: preset.DisplayNameZhHans,
			DisplayNameEn:     cloneDocumentString(preset.DisplayNameEn),
			Sort:              preset.Sort,
			Enabled:           preset.Enabled,
			DefaultStrength:   preset.DefaultStrength,
			Adjustments:       preset.Adjustments.model(),
		}
	}
	return model.Restore(model.Snapshot{
		ReleaseID:                    document.ReleaseID,
		Version:                      document.Version,
		SourceOwner:                  document.SourceOwner,
		CanonicalDigest:              document.CanonicalDigest,
		Status:                       model.Status(document.Status),
		CategoryCount:                document.CategoryCount,
		PresetCount:                  document.PresetCount,
		Categories:                   categories,
		Presets:                      presets,
		RecommendedFallbackPresetIDs: cloneDocumentStrings(document.RecommendedFallbackPresetIDs),
		ImportedAt:                   document.ImportedAt,
		ActivatedAt:                  cloneDocumentTime(document.ActivatedAt),
	})
}

func filterCatalogAdjustmentDocumentFromModel(
	values model.FilterAdjustmentValues,
) filterCatalogAdjustmentDocument {
	return filterCatalogAdjustmentDocument{
		LightSense:  values.LightSense,
		Brightness:  values.Brightness,
		Exposure:    values.Exposure,
		Contrast:    values.Contrast,
		Saturation:  values.Saturation,
		Vibrance:    values.Vibrance,
		Texture:     values.Texture,
		Sharpen:     values.Sharpen,
		Structure:   values.Structure,
		Highlight:   values.Highlight,
		Shadow:      values.Shadow,
		Temperature: values.Temperature,
		Tint:        values.Tint,
		Grain:       values.Grain,
		Fade:        values.Fade,
	}
}

func (document filterCatalogAdjustmentDocument) model() model.FilterAdjustmentValues {
	return model.FilterAdjustmentValues{
		LightSense:  document.LightSense,
		Brightness:  document.Brightness,
		Exposure:    document.Exposure,
		Contrast:    document.Contrast,
		Saturation:  document.Saturation,
		Vibrance:    document.Vibrance,
		Texture:     document.Texture,
		Sharpen:     document.Sharpen,
		Structure:   document.Structure,
		Highlight:   document.Highlight,
		Shadow:      document.Shadow,
		Temperature: document.Temperature,
		Tint:        document.Tint,
		Grain:       document.Grain,
		Fade:        document.Fade,
	}
}

func cloneDocumentString(value *string) *string {
	if value == nil {
		return nil
	}
	cloned := *value
	return &cloned
}

func cloneDocumentStrings(source []string) []string {
	if source == nil {
		return nil
	}
	cloned := make([]string, len(source))
	copy(cloned, source)
	return cloned
}

func cloneDocumentTime(value *time.Time) *time.Time {
	if value == nil {
		return nil
	}
	cloned := value.UTC()
	return &cloned
}
