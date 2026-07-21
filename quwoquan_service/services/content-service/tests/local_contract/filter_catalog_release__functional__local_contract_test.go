package local_contract

import (
	"errors"
	"testing"
	"time"

	filtercatalogmodel "quwoquan_service/services/content-service/internal/domain/content/filter_catalog_release/model"
)

func TestFilterCatalogStageValidatesCanonicalPayload(t *testing.T) {
	categories, presets, fallbacks := validFilterCatalogPayload()
	digest, err := filtercatalogmodel.ComputeCanonicalDigest(categories, presets, fallbacks)
	if err != nil {
		t.Fatalf("compute valid canonical digest: %v", err)
	}
	release, err := filtercatalogmodel.NewStaged(filtercatalogmodel.NewStagedParams{
		ReleaseID:                    "filter-release-valid",
		SourceOwner:                  "qwq-data",
		CanonicalDigest:              digest,
		Categories:                   categories,
		Presets:                      presets,
		RecommendedFallbackPresetIDs: fallbacks,
		ImportedAt:                   time.Date(2026, 7, 20, 12, 0, 0, 0, time.UTC),
	})
	if err != nil {
		t.Fatalf("new valid staged release: %v", err)
	}
	snapshot := release.Snapshot()
	if snapshot.Status != filtercatalogmodel.StatusStaged ||
		snapshot.Version != 1 ||
		snapshot.CategoryCount != len(categories) ||
		snapshot.PresetCount != len(presets) {
		t.Fatalf("unexpected staged release: %+v", snapshot)
	}
	if snapshot.Categories[0].CategoryID != "basic" ||
		snapshot.Presets[0].PresetID != "original" {
		t.Fatalf("catalog was not normalized to deterministic display order: %+v", snapshot)
	}

	_, err = filtercatalogmodel.NewStaged(filtercatalogmodel.NewStagedParams{
		ReleaseID:                    "filter-release-digest-mismatch",
		SourceOwner:                  "qwq-data",
		CanonicalDigest:              "0000000000000000000000000000000000000000000000000000000000000000",
		Categories:                   categories,
		Presets:                      presets,
		RecommendedFallbackPresetIDs: fallbacks,
		ImportedAt:                   time.Now(),
	})
	if !errors.Is(err, filtercatalogmodel.ErrDigestMismatch) {
		t.Fatalf("digest mismatch must be rejected, got %v", err)
	}

	testCases := []struct {
		name      string
		transform func(
			[]filtercatalogmodel.FilterCategoryDefinition,
			[]filtercatalogmodel.FilterPresetDefinition,
			[]string,
		)
	}{
		{
			name: "duplicate category id",
			transform: func(
				categories []filtercatalogmodel.FilterCategoryDefinition,
				_ []filtercatalogmodel.FilterPresetDefinition,
				_ []string,
			) {
				categories[1].CategoryID = categories[0].CategoryID
			},
		},
		{
			name: "duplicate category sort",
			transform: func(
				categories []filtercatalogmodel.FilterCategoryDefinition,
				_ []filtercatalogmodel.FilterPresetDefinition,
				_ []string,
			) {
				categories[1].Sort = categories[0].Sort
			},
		},
		{
			name: "unknown category reference",
			transform: func(
				_ []filtercatalogmodel.FilterCategoryDefinition,
				presets []filtercatalogmodel.FilterPresetDefinition,
				_ []string,
			) {
				presets[1].CategoryID = "missing"
			},
		},
		{
			name: "enabled preset in disabled category",
			transform: func(
				categories []filtercatalogmodel.FilterCategoryDefinition,
				_ []filtercatalogmodel.FilterPresetDefinition,
				_ []string,
			) {
				categories[1].Enabled = false
			},
		},
		{
			name: "duplicate preset id",
			transform: func(
				_ []filtercatalogmodel.FilterCategoryDefinition,
				presets []filtercatalogmodel.FilterPresetDefinition,
				_ []string,
			) {
				presets[1].PresetID = presets[0].PresetID
			},
		},
		{
			name: "duplicate sort in category",
			transform: func(
				_ []filtercatalogmodel.FilterCategoryDefinition,
				presets []filtercatalogmodel.FilterPresetDefinition,
				_ []string,
			) {
				presets[1].CategoryID = presets[0].CategoryID
				presets[1].Sort = presets[0].Sort
			},
		},
		{
			name: "original is not identity",
			transform: func(
				_ []filtercatalogmodel.FilterCategoryDefinition,
				presets []filtercatalogmodel.FilterPresetDefinition,
				_ []string,
			) {
				presets[1].Adjustments.Contrast = 1
			},
		},
		{
			name: "original is disabled",
			transform: func(
				_ []filtercatalogmodel.FilterCategoryDefinition,
				presets []filtercatalogmodel.FilterPresetDefinition,
				_ []string,
			) {
				presets[1].Enabled = false
			},
		},
		{
			name: "canonical text has surrounding whitespace",
			transform: func(
				categories []filtercatalogmodel.FilterCategoryDefinition,
				_ []filtercatalogmodel.FilterPresetDefinition,
				_ []string,
			) {
				categories[0].DisplayNameZhHans = " 人像"
			},
		},
		{
			name: "adjustment out of range",
			transform: func(
				_ []filtercatalogmodel.FilterCategoryDefinition,
				presets []filtercatalogmodel.FilterPresetDefinition,
				_ []string,
			) {
				presets[1].Adjustments.Saturation = 101
			},
		},
		{
			name: "duplicate fallback",
			transform: func(
				_ []filtercatalogmodel.FilterCategoryDefinition,
				_ []filtercatalogmodel.FilterPresetDefinition,
				fallbacks []string,
			) {
				fallbacks[1] = fallbacks[0]
			},
		},
	}
	for _, testCase := range testCases {
		t.Run(testCase.name, func(t *testing.T) {
			testCategories, testPresets, testFallbacks := validFilterCatalogPayload()
			testCase.transform(testCategories, testPresets, testFallbacks)
			if _, err := filtercatalogmodel.ComputeCanonicalDigest(
				testCategories,
				testPresets,
				testFallbacks,
			); !errors.Is(err, filtercatalogmodel.ErrInvalidArgument) {
				t.Fatalf("invalid payload must fail with ErrInvalidArgument, got %v", err)
			}
		})
	}
}

func TestFilterCatalogCanonicalDigestIsOrderStableAndSnapshotImmutable(t *testing.T) {
	categories, presets, fallbacks := validFilterCatalogPayload()
	firstDigest, err := filtercatalogmodel.ComputeCanonicalDigest(categories, presets, fallbacks)
	if err != nil {
		t.Fatal(err)
	}
	reverseCategories(categories)
	reversePresets(presets)
	secondDigest, err := filtercatalogmodel.ComputeCanonicalDigest(categories, presets, fallbacks)
	if err != nil {
		t.Fatal(err)
	}
	if firstDigest != secondDigest {
		t.Fatalf("canonical digest depends on input array order: %s != %s", firstDigest, secondDigest)
	}
	const expectedCanonicalDigest = "255ea3ff2b53ec371b362f57f88c75981b737ff31bc7d2fc98839420c8e823fb"
	if firstDigest != expectedCanonicalDigest {
		t.Fatalf(
			"canonical digest differs from independent data-plane vector: got %s want %s",
			firstDigest,
			expectedCanonicalDigest,
		)
	}

	release, err := filtercatalogmodel.NewStaged(filtercatalogmodel.NewStagedParams{
		ReleaseID:                    "filter-release-immutable",
		SourceOwner:                  "qwq-data",
		CanonicalDigest:              firstDigest,
		Categories:                   categories,
		Presets:                      presets,
		RecommendedFallbackPresetIDs: fallbacks,
		ImportedAt:                   time.Now(),
	})
	if err != nil {
		t.Fatal(err)
	}
	snapshot := release.Snapshot()
	snapshot.Categories[0].CategoryID = "mutated"
	snapshot.Presets[0].Adjustments.Contrast = 99
	snapshot.RecommendedFallbackPresetIDs[0] = "mutated"
	restored := release.Snapshot()
	if restored.Categories[0].CategoryID == "mutated" ||
		restored.Presets[0].Adjustments.Contrast == 99 ||
		restored.RecommendedFallbackPresetIDs[0] == "mutated" {
		t.Fatal("snapshot mutation leaked into immutable FilterCatalogRelease")
	}
}

func TestFilterCatalogCanonicalDigestMatchesDecimalBoundaryVector(t *testing.T) {
	categories := []filtercatalogmodel.FilterCategoryDefinition{
		{
			CategoryID:        "camera_photo",
			DisplayNameZhHans: "拍照",
			Sort:              1,
			Enabled:           true,
		},
	}
	presets := []filtercatalogmodel.FilterPresetDefinition{
		{
			PresetID:          "original",
			CategoryID:        "camera_photo",
			DisplayNameZhHans: "原图",
			Sort:              1,
			Enabled:           true,
			DefaultStrength:   0,
		},
		{
			PresetID:          "cinema",
			CategoryID:        "camera_photo",
			DisplayNameZhHans: "电影",
			DisplayNameEn:     filterCatalogString("Cinema"),
			Sort:              2,
			Enabled:           true,
			DefaultStrength:   80.5,
			Adjustments: filtercatalogmodel.FilterAdjustmentValues{
				Contrast:    8.25,
				Temperature: -12.5,
				Grain:       0.0000001,
				Fade:        -0.0,
			},
		},
	}

	digest, err := filtercatalogmodel.ComputeCanonicalDigest(
		categories,
		presets,
		[]string{"cinema"},
	)
	if err != nil {
		t.Fatalf("compute decimal boundary vector digest: %v", err)
	}
	const expected = "fba38ede15295f3bbee31375d9955edc0baf722b8c204dbf0575f4ab25401242"
	if digest != expected {
		t.Fatalf("decimal boundary digest drift: got %s want %s", digest, expected)
	}
}

func validFilterCatalogPayload() (
	[]filtercatalogmodel.FilterCategoryDefinition,
	[]filtercatalogmodel.FilterPresetDefinition,
	[]string,
) {
	categories := []filtercatalogmodel.FilterCategoryDefinition{
		{
			CategoryID:        "portrait",
			DisplayNameZhHans: "人像",
			DisplayNameEn:     filterCatalogString("Portrait <&"),
			Sort:              20,
			Enabled:           true,
		},
		{
			CategoryID:        "basic",
			DisplayNameZhHans: "基础",
			Sort:              10,
			Enabled:           true,
		},
	}
	presets := []filtercatalogmodel.FilterPresetDefinition{
		{
			PresetID:          "soft-portrait",
			CategoryID:        "portrait",
			DisplayNameZhHans: "柔光人像",
			DisplayNameEn:     filterCatalogString("Soft\u2028Portrait"),
			Sort:              1,
			Enabled:           true,
			DefaultStrength:   80.5,
			Adjustments: filtercatalogmodel.FilterAdjustmentValues{
				LightSense: 0.0000001,
				Contrast:   -4.25,
			},
		},
		{
			PresetID:          "original",
			CategoryID:        "basic",
			DisplayNameZhHans: "原图",
			Sort:              1,
			Enabled:           true,
			DefaultStrength:   0,
		},
	}
	return categories, presets, []string{"original", "soft-portrait"}
}

func filterCatalogString(value string) *string {
	return &value
}

func reverseCategories(values []filtercatalogmodel.FilterCategoryDefinition) {
	for left, right := 0, len(values)-1; left < right; left, right = left+1, right-1 {
		values[left], values[right] = values[right], values[left]
	}
}

func reversePresets(values []filtercatalogmodel.FilterPresetDefinition) {
	for left, right := 0, len(values)-1; left < right; left, right = left+1, right-1 {
		values[left], values[right] = values[right], values[left]
	}
}
