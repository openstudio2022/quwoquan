package model

import (
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"math"
	"sort"
	"strings"
	"unicode/utf8"
)

const (
	minCategoryCount = 1
	maxCategoryCount = 32
	minPresetCount   = 1
	maxPresetCount   = 256
)

// FilterCategoryDefinition 是 FilterCatalogRelease 内的有界分类成员。
type FilterCategoryDefinition struct {
	CategoryID        string  `json:"categoryId"`
	DisplayNameZhHans string  `json:"displayNameZhHans"`
	DisplayNameEn     *string `json:"displayNameEn"`
	Sort              int     `json:"sort"`
	Enabled           bool    `json:"enabled"`
}

// FilterAdjustmentValues 是滤镜预设允许表达的完整 15 项强类型参数。
type FilterAdjustmentValues struct {
	LightSense  float64 `json:"lightSense"`
	Brightness  float64 `json:"brightness"`
	Exposure    float64 `json:"exposure"`
	Contrast    float64 `json:"contrast"`
	Saturation  float64 `json:"saturation"`
	Vibrance    float64 `json:"vibrance"`
	Texture     float64 `json:"texture"`
	Sharpen     float64 `json:"sharpen"`
	Structure   float64 `json:"structure"`
	Highlight   float64 `json:"highlight"`
	Shadow      float64 `json:"shadow"`
	Temperature float64 `json:"temperature"`
	Tint        float64 `json:"tint"`
	Grain       float64 `json:"grain"`
	Fade        float64 `json:"fade"`
}

// FilterPresetDefinition 是 FilterCatalogRelease 内的有界预设成员。
type FilterPresetDefinition struct {
	PresetID          string                 `json:"presetId"`
	CategoryID        string                 `json:"categoryId"`
	DisplayNameZhHans string                 `json:"displayNameZhHans"`
	DisplayNameEn     *string                `json:"displayNameEn"`
	Sort              int                    `json:"sort"`
	Enabled           bool                   `json:"enabled"`
	DefaultStrength   float64                `json:"defaultStrength"`
	Adjustments       FilterAdjustmentValues `json:"adjustments"`
}

type canonicalCatalogPayload struct {
	Categories                   []FilterCategoryDefinition `json:"categories"`
	Presets                      []FilterPresetDefinition   `json:"presets"`
	RecommendedFallbackPresetIDs []string                   `json:"recommendedFallbackPresetIds"`
}

func normalizeAndValidateCatalog(
	categories []FilterCategoryDefinition,
	presets []FilterPresetDefinition,
	recommendedFallbackPresetIDs []string,
) (canonicalCatalogPayload, error) {
	if len(categories) < minCategoryCount || len(categories) > maxCategoryCount {
		return canonicalCatalogPayload{}, fmt.Errorf(
			"%w: categories count must be %d..%d",
			ErrInvalidArgument,
			minCategoryCount,
			maxCategoryCount,
		)
	}
	if len(presets) < minPresetCount || len(presets) > maxPresetCount {
		return canonicalCatalogPayload{}, fmt.Errorf(
			"%w: presets count must be %d..%d",
			ErrInvalidArgument,
			minPresetCount,
			maxPresetCount,
		)
	}
	if recommendedFallbackPresetIDs == nil {
		return canonicalCatalogPayload{}, fmt.Errorf(
			"%w: recommendedFallbackPresetIds must be an array",
			ErrInvalidArgument,
		)
	}

	normalizedCategories := make([]FilterCategoryDefinition, len(categories))
	categoryByID := make(map[string]FilterCategoryDefinition, len(categories))
	for index, category := range categories {
		if !validCanonicalText(category.CategoryID) ||
			!validCanonicalText(category.DisplayNameZhHans) ||
			!validOptionalCanonicalText(category.DisplayNameEn) {
			return canonicalCatalogPayload{}, fmt.Errorf(
				"%w: category text must be valid UTF-8 without surrounding whitespace",
				ErrInvalidArgument,
			)
		}
		category.DisplayNameEn = cloneString(category.DisplayNameEn)
		if _, duplicated := categoryByID[category.CategoryID]; duplicated {
			return canonicalCatalogPayload{}, fmt.Errorf(
				"%w: duplicate categoryId %q",
				ErrInvalidArgument,
				category.CategoryID,
			)
		}
		categoryByID[category.CategoryID] = category
		normalizedCategories[index] = category
	}
	sort.Slice(normalizedCategories, func(left, right int) bool {
		if normalizedCategories[left].Sort != normalizedCategories[right].Sort {
			return normalizedCategories[left].Sort < normalizedCategories[right].Sort
		}
		return normalizedCategories[left].CategoryID < normalizedCategories[right].CategoryID
	})

	normalizedPresets := make([]FilterPresetDefinition, len(presets))
	presetByID := make(map[string]FilterPresetDefinition, len(presets))
	sortByCategory := make(map[string]map[int]string, len(categories))
	for index, preset := range presets {
		preset.DefaultStrength = normalizeZero(preset.DefaultStrength)
		preset.Adjustments = normalizeAdjustments(preset.Adjustments)
		if !validCanonicalText(preset.PresetID) ||
			!validCanonicalText(preset.CategoryID) ||
			!validCanonicalText(preset.DisplayNameZhHans) ||
			!validOptionalCanonicalText(preset.DisplayNameEn) {
			return canonicalCatalogPayload{}, fmt.Errorf(
				"%w: preset text must be valid UTF-8 without surrounding whitespace",
				ErrInvalidArgument,
			)
		}
		preset.DisplayNameEn = cloneString(preset.DisplayNameEn)
		category, categoryFound := categoryByID[preset.CategoryID]
		if !categoryFound {
			return canonicalCatalogPayload{}, fmt.Errorf(
				"%w: preset %q references unknown category %q",
				ErrInvalidArgument,
				preset.PresetID,
				preset.CategoryID,
			)
		}
		if preset.Enabled && !category.Enabled {
			return canonicalCatalogPayload{}, fmt.Errorf(
				"%w: enabled preset %q references disabled category %q",
				ErrInvalidArgument,
				preset.PresetID,
				preset.CategoryID,
			)
		}
		if _, duplicated := presetByID[preset.PresetID]; duplicated {
			return canonicalCatalogPayload{}, fmt.Errorf(
				"%w: duplicate presetId %q",
				ErrInvalidArgument,
				preset.PresetID,
			)
		}
		if !isFiniteInRange(preset.DefaultStrength, 0, 100) {
			return canonicalCatalogPayload{}, fmt.Errorf(
				"%w: preset %q defaultStrength must be within 0..100",
				ErrInvalidArgument,
				preset.PresetID,
			)
		}
		if err := validateAdjustments(preset.PresetID, preset.Adjustments); err != nil {
			return canonicalCatalogPayload{}, err
		}
		categorySorts := sortByCategory[preset.CategoryID]
		if categorySorts == nil {
			categorySorts = make(map[int]string)
			sortByCategory[preset.CategoryID] = categorySorts
		}
		if existingID, duplicated := categorySorts[preset.Sort]; duplicated {
			return canonicalCatalogPayload{}, fmt.Errorf(
				"%w: presets %q and %q share sort %d in category %q",
				ErrInvalidArgument,
				existingID,
				preset.PresetID,
				preset.Sort,
				preset.CategoryID,
			)
		}
		categorySorts[preset.Sort] = preset.PresetID
		presetByID[preset.PresetID] = preset
		normalizedPresets[index] = preset
	}

	original, originalFound := presetByID["original"]
	if !originalFound ||
		!original.Enabled ||
		original.DefaultStrength != 0 ||
		!original.Adjustments.IsIdentity() {
		return canonicalCatalogPayload{}, fmt.Errorf(
			"%w: original preset must be enabled with zero strength and identity adjustments",
			ErrInvalidArgument,
		)
	}

	sort.Slice(normalizedPresets, func(left, right int) bool {
		leftPreset := normalizedPresets[left]
		rightPreset := normalizedPresets[right]
		if leftPreset.CategoryID != rightPreset.CategoryID {
			return leftPreset.CategoryID < rightPreset.CategoryID
		}
		if leftPreset.Sort != rightPreset.Sort {
			return leftPreset.Sort < rightPreset.Sort
		}
		return leftPreset.PresetID < rightPreset.PresetID
	})

	normalizedFallbacks := make([]string, len(recommendedFallbackPresetIDs))
	seenFallbacks := make(map[string]struct{}, len(recommendedFallbackPresetIDs))
	for index, presetID := range recommendedFallbackPresetIDs {
		if !validCanonicalText(presetID) {
			return canonicalCatalogPayload{}, fmt.Errorf(
				"%w: recommended fallback must be valid UTF-8 without surrounding whitespace",
				ErrInvalidArgument,
			)
		}
		preset, found := presetByID[presetID]
		if !found || !preset.Enabled {
			return canonicalCatalogPayload{}, fmt.Errorf(
				"%w: recommended fallback %q must reference an enabled preset",
				ErrInvalidArgument,
				presetID,
			)
		}
		if _, duplicated := seenFallbacks[presetID]; duplicated {
			return canonicalCatalogPayload{}, fmt.Errorf(
				"%w: duplicate recommended fallback %q",
				ErrInvalidArgument,
				presetID,
			)
		}
		seenFallbacks[presetID] = struct{}{}
		normalizedFallbacks[index] = presetID
	}

	return canonicalCatalogPayload{
		Categories:                   normalizedCategories,
		Presets:                      normalizedPresets,
		RecommendedFallbackPresetIDs: normalizedFallbacks,
	}, nil
}

// ComputeCanonicalDigest 计算 categories/presets/recommended payload 的规范
// SHA-256。分类和预设先按其展示顺序稳定排序，推荐列表保留业务优先级顺序。
func ComputeCanonicalDigest(
	categories []FilterCategoryDefinition,
	presets []FilterPresetDefinition,
	recommendedFallbackPresetIDs []string,
) (string, error) {
	payload, err := normalizeAndValidateCatalog(
		categories,
		presets,
		recommendedFallbackPresetIDs,
	)
	if err != nil {
		return "", err
	}
	encoded, err := encodeCanonicalCatalog(payload)
	if err != nil {
		return "", fmt.Errorf("%w: encode canonical payload: %v", ErrInvalidArgument, err)
	}
	sum := sha256.Sum256(encoded)
	return hex.EncodeToString(sum[:]), nil
}

func (values FilterAdjustmentValues) IsIdentity() bool {
	return values.LightSense == 0 &&
		values.Brightness == 0 &&
		values.Exposure == 0 &&
		values.Contrast == 0 &&
		values.Saturation == 0 &&
		values.Vibrance == 0 &&
		values.Texture == 0 &&
		values.Sharpen == 0 &&
		values.Structure == 0 &&
		values.Highlight == 0 &&
		values.Shadow == 0 &&
		values.Temperature == 0 &&
		values.Tint == 0 &&
		values.Grain == 0 &&
		values.Fade == 0
}

func validateAdjustments(presetID string, values FilterAdjustmentValues) error {
	fields := []struct {
		name  string
		value float64
	}{
		{name: "lightSense", value: values.LightSense},
		{name: "brightness", value: values.Brightness},
		{name: "exposure", value: values.Exposure},
		{name: "contrast", value: values.Contrast},
		{name: "saturation", value: values.Saturation},
		{name: "vibrance", value: values.Vibrance},
		{name: "texture", value: values.Texture},
		{name: "sharpen", value: values.Sharpen},
		{name: "structure", value: values.Structure},
		{name: "highlight", value: values.Highlight},
		{name: "shadow", value: values.Shadow},
		{name: "temperature", value: values.Temperature},
		{name: "tint", value: values.Tint},
		{name: "grain", value: values.Grain},
		{name: "fade", value: values.Fade},
	}
	for _, field := range fields {
		if !isFiniteInRange(field.value, -100, 100) {
			return fmt.Errorf(
				"%w: preset %q adjustment %s must be within -100..100",
				ErrInvalidArgument,
				presetID,
				field.name,
			)
		}
	}
	return nil
}

func normalizeAdjustments(values FilterAdjustmentValues) FilterAdjustmentValues {
	values.LightSense = normalizeZero(values.LightSense)
	values.Brightness = normalizeZero(values.Brightness)
	values.Exposure = normalizeZero(values.Exposure)
	values.Contrast = normalizeZero(values.Contrast)
	values.Saturation = normalizeZero(values.Saturation)
	values.Vibrance = normalizeZero(values.Vibrance)
	values.Texture = normalizeZero(values.Texture)
	values.Sharpen = normalizeZero(values.Sharpen)
	values.Structure = normalizeZero(values.Structure)
	values.Highlight = normalizeZero(values.Highlight)
	values.Shadow = normalizeZero(values.Shadow)
	values.Temperature = normalizeZero(values.Temperature)
	values.Tint = normalizeZero(values.Tint)
	values.Grain = normalizeZero(values.Grain)
	values.Fade = normalizeZero(values.Fade)
	return values
}

func validCanonicalText(value string) bool {
	return value != "" &&
		utf8.ValidString(value) &&
		value == strings.TrimSpace(value)
}

func validOptionalCanonicalText(value *string) bool {
	return value == nil || validCanonicalText(*value)
}

func normalizeZero(value float64) float64 {
	if value == 0 {
		return 0
	}
	return value
}

func isFiniteInRange(value, minimum, maximum float64) bool {
	return !math.IsNaN(value) &&
		!math.IsInf(value, 0) &&
		value >= minimum &&
		value <= maximum
}
