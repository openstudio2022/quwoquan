package http

import (
	"bytes"
	"encoding/json"
	"fmt"
	"net/http"
	"sort"
)

var filterCatalogAdjustmentFields = []string{
	"lightSense",
	"brightness",
	"exposure",
	"contrast",
	"saturation",
	"vibrance",
	"texture",
	"sharpen",
	"structure",
	"highlight",
	"shadow",
	"temperature",
	"tint",
	"grain",
	"fade",
}

func decodeFilterCatalogStageBody(
	request *http.Request,
) (stageFilterCatalogReleaseBody, error) {
	var raw json.RawMessage
	if err := decodeRequiredJSONBody(request, &raw); err != nil {
		return stageFilterCatalogReleaseBody{}, err
	}
	if err := validateFilterCatalogStageJSON(raw); err != nil {
		return stageFilterCatalogReleaseBody{}, err
	}
	var body stageFilterCatalogReleaseBody
	if err := json.Unmarshal(raw, &body); err != nil {
		return stageFilterCatalogReleaseBody{}, fmt.Errorf(
			"decode typed FilterCatalogRelease body: %w",
			err,
		)
	}
	return body, nil
}

func validateFilterCatalogStageJSON(raw json.RawMessage) error {
	root, err := requireExactFilterCatalogObject(
		raw,
		"FilterCatalogRelease",
		"releaseId",
		"sourceOwner",
		"canonicalDigest",
		"categories",
		"presets",
		"recommendedFallbackPresetIds",
	)
	if err != nil {
		return err
	}
	if err := requireNonNullFilterCatalogFields(
		root,
		"FilterCatalogRelease",
		"releaseId",
		"sourceOwner",
		"canonicalDigest",
	); err != nil {
		return err
	}
	categories, err := requireFilterCatalogArray(
		root["categories"],
		"FilterCatalogRelease.categories",
	)
	if err != nil {
		return err
	}
	for index, category := range categories {
		label := fmt.Sprintf("FilterCatalogRelease.categories[%d]", index)
		categoryObject, objectErr := requireExactFilterCatalogObject(
			category,
			label,
			"categoryId",
			"displayNameZhHans",
			"displayNameEn",
			"sort",
			"enabled",
		)
		if objectErr != nil {
			return objectErr
		}
		if objectErr = requireNonNullFilterCatalogFields(
			categoryObject,
			label,
			"categoryId",
			"displayNameZhHans",
			"sort",
			"enabled",
		); objectErr != nil {
			return objectErr
		}
	}
	presets, err := requireFilterCatalogArray(
		root["presets"],
		"FilterCatalogRelease.presets",
	)
	if err != nil {
		return err
	}
	for index, preset := range presets {
		label := fmt.Sprintf("FilterCatalogRelease.presets[%d]", index)
		presetObject, objectErr := requireExactFilterCatalogObject(
			preset,
			label,
			"presetId",
			"categoryId",
			"displayNameZhHans",
			"displayNameEn",
			"sort",
			"enabled",
			"defaultStrength",
			"adjustments",
		)
		if objectErr != nil {
			return objectErr
		}
		if objectErr = requireNonNullFilterCatalogFields(
			presetObject,
			label,
			"presetId",
			"categoryId",
			"displayNameZhHans",
			"sort",
			"enabled",
			"defaultStrength",
		); objectErr != nil {
			return objectErr
		}
		adjustments, objectErr := requireExactFilterCatalogObject(
			presetObject["adjustments"],
			label+".adjustments",
			filterCatalogAdjustmentFields...,
		)
		if objectErr != nil {
			return objectErr
		}
		if objectErr = requireNonNullFilterCatalogFields(
			adjustments,
			label+".adjustments",
			filterCatalogAdjustmentFields...,
		); objectErr != nil {
			return objectErr
		}
	}
	_, err = requireFilterCatalogArray(
		root["recommendedFallbackPresetIds"],
		"FilterCatalogRelease.recommendedFallbackPresetIds",
	)
	return err
}

func requireExactFilterCatalogObject(
	raw json.RawMessage,
	label string,
	expectedFields ...string,
) (map[string]json.RawMessage, error) {
	var object map[string]json.RawMessage
	if len(raw) == 0 || string(raw) == "null" || json.Unmarshal(raw, &object) != nil || object == nil {
		return nil, fmt.Errorf("%s must be an object", label)
	}
	expected := make(map[string]struct{}, len(expectedFields))
	for _, field := range expectedFields {
		expected[field] = struct{}{}
	}
	var missing []string
	for field := range expected {
		if _, found := object[field]; !found {
			missing = append(missing, field)
		}
	}
	var unknown []string
	for field := range object {
		if _, found := expected[field]; !found {
			unknown = append(unknown, field)
		}
	}
	if len(missing) > 0 || len(unknown) > 0 {
		sort.Strings(missing)
		sort.Strings(unknown)
		return nil, fmt.Errorf(
			"%s fields are invalid: missing=%v unknown=%v",
			label,
			missing,
			unknown,
		)
	}
	return object, nil
}

func requireNonNullFilterCatalogFields(
	object map[string]json.RawMessage,
	label string,
	fields ...string,
) error {
	for _, field := range fields {
		if bytes.Equal(bytes.TrimSpace(object[field]), []byte("null")) {
			return fmt.Errorf("%s.%s must not be null", label, field)
		}
	}
	return nil
}

func requireFilterCatalogArray(
	raw json.RawMessage,
	label string,
) ([]json.RawMessage, error) {
	var values []json.RawMessage
	if len(raw) == 0 || string(raw) == "null" || json.Unmarshal(raw, &values) != nil || values == nil {
		return nil, fmt.Errorf("%s must be an array", label)
	}
	return values, nil
}
