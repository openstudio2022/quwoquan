package main

import (
	"errors"
	"fmt"
	"reflect"
	"sort"
	"strings"
)

type appClientBundleBinding struct {
	BundleID                string            `json:"bundleId"`
	Role                    string            `json:"role"`
	SupportedContentTypes   []string          `json:"supportedContentTypes,omitempty"`
	RequiredForContentTypes []string          `json:"requiredForContentTypes,omitempty"`
	SelectedFields          []string          `json:"selectedFields"`
	AssemblyMappings        []assemblyMapping `json:"assemblyMappings"`
}

type assemblyMapping struct {
	TargetField         string           `json:"targetField"`
	PresenceSourceField string           `json:"presenceSourceField,omitempty"`
	Sources             []assemblySource `json:"sources"`
}

type assemblySource struct {
	SourceField string `json:"sourceField"`
	Strategy    string `json:"strategy"`
	TargetKey   string `json:"targetKey,omitempty"`
}

type bundleSliceInput struct {
	OperationName  string
	Binding        appClientBundleBinding
	SelectedFields []string
}

type detailBundlePlan struct {
	Base                  bundleSliceInput
	Extensions            []bundleSliceInput
	SupportedContentTypes []string
	AssemblyProjectionID  string
	AssemblyMappings      []assemblyMapping
}

func validateDetailBundle(slices []bundleSliceInput, projectionFields []string, projectionID string) (detailBundlePlan, error) {
	if len(slices) < 1 || len(projectionFields) < 1 || strings.TrimSpace(projectionID) == "" {
		return detailBundlePlan{}, errors.New("ContentPostDetail App bundle and projection are required")
	}
	var bases []bundleSliceInput
	extensions := make([]bundleSliceInput, 0)
	allMappings := make([]assemblyMapping, 0)
	seenTargets := map[string]bool{}
	seenSources := map[string]bool{}
	for _, slice := range slices {
		if err := validateBundleBindingShape(slice.Binding); err != nil {
			return detailBundlePlan{}, fmt.Errorf("operation %s: %w", slice.OperationName, err)
		}
		if !reflect.DeepEqual(slice.Binding.SelectedFields, slice.SelectedFields) {
			return detailBundlePlan{}, fmt.Errorf("operation %s AST selected fields differ from signed registry bundle", slice.OperationName)
		}
		if err := validateMappings(slice.Binding.AssemblyMappings); err != nil {
			return detailBundlePlan{}, fmt.Errorf("operation %s: %w", slice.OperationName, err)
		}
		for _, mapping := range slice.Binding.AssemblyMappings {
			if seenTargets[mapping.TargetField] {
				return detailBundlePlan{}, fmt.Errorf("assembly target %s is duplicated across bundle entries", mapping.TargetField)
			}
			seenTargets[mapping.TargetField] = true
			for _, source := range mapping.Sources {
				if seenSources[source.SourceField] {
					return detailBundlePlan{}, fmt.Errorf("assembly source %s is consumed across bundle entries", source.SourceField)
				}
				seenSources[source.SourceField] = true
				if !containsString(slice.SelectedFields, source.SourceField) {
					return detailBundlePlan{}, fmt.Errorf("assembly source %s is absent from operation %s", source.SourceField, slice.OperationName)
				}
			}
			allMappings = append(allMappings, mapping)
		}
		switch slice.Binding.Role {
		case "base":
			bases = append(bases, slice)
		case "extension":
			extensions = append(extensions, slice)
		default:
			return detailBundlePlan{}, fmt.Errorf("operation %s has unsupported bundle role %q", slice.OperationName, slice.Binding.Role)
		}
	}
	if len(bases) != 1 {
		return detailBundlePlan{}, fmt.Errorf("ContentPostDetail bundle requires exactly one base, got %d", len(bases))
	}
	base := bases[0]
	baseBinding := base.Binding
	if !containsString(base.SelectedFields, "contentType") {
		return detailBundlePlan{}, errors.New("ContentPostDetail bundle base must select contentType")
	}
	supported := stringSet(baseBinding.SupportedContentTypes)
	for _, extension := range extensions {
		if extension.Binding.BundleID != baseBinding.BundleID {
			return detailBundlePlan{}, fmt.Errorf("operation %s bundleId differs from base", extension.OperationName)
		}
		for _, contentType := range extension.Binding.RequiredForContentTypes {
			if !supported[contentType] {
				return detailBundlePlan{}, fmt.Errorf("operation %s content type %s is outside base supportedContentTypes", extension.OperationName, contentType)
			}
		}
	}
	sort.Slice(extensions, func(left, right int) bool { return extensions[left].OperationName < extensions[right].OperationName })
	sort.Slice(allMappings, func(left, right int) bool { return allMappings[left].TargetField < allMappings[right].TargetField })
	for _, contentType := range baseBinding.SupportedContentTypes {
		assembled, err := assembledFieldSet(contentType, base, extensions, allMappings)
		if err != nil {
			return detailBundlePlan{}, err
		}
		if extra := extraFields(projectionFields, assembled); len(extra) != 0 {
			return detailBundlePlan{}, fmt.Errorf("content type %s exposes fields outside assembly projection: %s", contentType, strings.Join(extra, ", "))
		}
	}
	allFields, err := assembledAllFieldSet(base, extensions, allMappings)
	if err != nil {
		return detailBundlePlan{}, err
	}
	if missing := missingFields(projectionFields, allFields); len(missing) != 0 {
		return detailBundlePlan{}, fmt.Errorf("signed bundle is missing assembly projection fields: %s", strings.Join(missing, ", "))
	}
	if extra := extraFields(projectionFields, allFields); len(extra) != 0 {
		return detailBundlePlan{}, fmt.Errorf("signed bundle exposes fields outside assembly projection: %s", strings.Join(extra, ", "))
	}
	return detailBundlePlan{
		Base: base, Extensions: extensions,
		SupportedContentTypes: append([]string(nil), baseBinding.SupportedContentTypes...),
		AssemblyProjectionID:  projectionID, AssemblyMappings: allMappings,
	}, nil
}

func validateBundleBindingShape(binding appClientBundleBinding) error {
	if strings.TrimSpace(binding.BundleID) == "" {
		return errors.New("bundleId is required")
	}
	if err := validateSortedUniqueStrings(binding.SelectedFields, "selectedFields"); err != nil {
		return err
	}
	switch binding.Role {
	case "base":
		if len(binding.SupportedContentTypes) == 0 || len(binding.RequiredForContentTypes) != 0 {
			return errors.New("base requires supportedContentTypes and forbids requiredForContentTypes")
		}
		return validateSortedUniqueStrings(binding.SupportedContentTypes, "supportedContentTypes")
	case "extension":
		if len(binding.SupportedContentTypes) != 0 || len(binding.RequiredForContentTypes) == 0 {
			return errors.New("extension requires requiredForContentTypes and forbids supportedContentTypes")
		}
		return validateSortedUniqueStrings(binding.RequiredForContentTypes, "requiredForContentTypes")
	default:
		return fmt.Errorf("unsupported bundle role %q", binding.Role)
	}
}

func validateMappings(mappings []assemblyMapping) error {
	targets := map[string]bool{}
	sources := map[string]bool{}
	for _, mapping := range mappings {
		if strings.TrimSpace(mapping.TargetField) == "" || len(mapping.Sources) == 0 || targets[mapping.TargetField] {
			return fmt.Errorf("assembly target field %q is empty or duplicated", mapping.TargetField)
		}
		targets[mapping.TargetField] = true
		hasReplace := false
		presenceFound := mapping.PresenceSourceField == ""
		for _, source := range mapping.Sources {
			if strings.TrimSpace(source.SourceField) == "" || sources[source.SourceField] {
				return fmt.Errorf("assembly source field %q is empty or consumed more than once", source.SourceField)
			}
			sources[source.SourceField] = true
			presenceFound = presenceFound || source.SourceField == mapping.PresenceSourceField
			switch source.Strategy {
			case "merge_object", "replace":
				hasReplace = hasReplace || source.Strategy == "replace"
				if source.TargetKey != "" {
					return fmt.Errorf("assembly strategy %s forbids targetKey", source.Strategy)
				}
			case "assign_key":
				if strings.TrimSpace(source.TargetKey) == "" {
					return errors.New("assembly assign_key requires targetKey")
				}
			default:
				return fmt.Errorf("unsupported assembly strategy %q", source.Strategy)
			}
		}
		if hasReplace && len(mapping.Sources) != 1 {
			return fmt.Errorf("assembly replace for %s must be the only source", mapping.TargetField)
		}
		if !presenceFound {
			return fmt.Errorf("assembly presenceSourceField %s is not a mapping source", mapping.PresenceSourceField)
		}
	}
	return nil
}

func assembledFieldSet(contentType string, base bundleSliceInput, extensions []bundleSliceInput, mappings []assemblyMapping) (map[string]bool, error) {
	selected := []bundleSliceInput{base}
	for _, extension := range extensions {
		if containsString(extension.Binding.RequiredForContentTypes, contentType) {
			selected = append(selected, extension)
		}
	}
	return assembledFieldSetForSlices("content type "+contentType, selected, mappings)
}

func assembledAllFieldSet(base bundleSliceInput, extensions []bundleSliceInput, mappings []assemblyMapping) (map[string]bool, error) {
	selected := append([]bundleSliceInput{base}, extensions...)
	return assembledFieldSetForSlices("signed bundle", selected, mappings)
}

func assembledFieldSetForSlices(label string, slices []bundleSliceInput, mappings []assemblyMapping) (map[string]bool, error) {
	counts := map[string]int{}
	for _, slice := range slices {
		for _, field := range slice.SelectedFields {
			counts[field]++
		}
	}
	for _, mapping := range mappings {
		present := 0
		for _, source := range mapping.Sources {
			if counts[source.SourceField] > 0 {
				present++
			}
		}
		if present == 0 {
			continue
		}
		if present != len(mapping.Sources) {
			return nil, fmt.Errorf("%s has partial assembly mapping for %s", label, mapping.TargetField)
		}
		if counts[mapping.TargetField] != 0 {
			return nil, fmt.Errorf("%s has assembly target conflict %s", label, mapping.TargetField)
		}
		for _, source := range mapping.Sources {
			delete(counts, source.SourceField)
		}
		counts[mapping.TargetField] = 1
	}
	assembled := make(map[string]bool, len(counts))
	for field := range counts {
		assembled[field] = true
	}
	return assembled, nil
}

func validateSortedUniqueStrings(values []string, label string) error {
	for index, value := range values {
		if strings.TrimSpace(value) == "" || index > 0 && values[index-1] >= value {
			return fmt.Errorf("%s must be non-empty, unique and sorted", label)
		}
	}
	return nil
}

func stringSet(values []string) map[string]bool {
	result := make(map[string]bool, len(values))
	for _, value := range values {
		result[value] = true
	}
	return result
}

func containsString(values []string, target string) bool {
	for _, value := range values {
		if value == target {
			return true
		}
	}
	return false
}
