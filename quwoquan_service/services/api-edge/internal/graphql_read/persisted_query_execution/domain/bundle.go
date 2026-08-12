package domain

import (
	"errors"
	"fmt"
	"regexp"
	"sort"
)

var contentTypePattern = regexp.MustCompile(`^[a-z][a-z0-9_]*$`)

type AppClientBundle struct {
	BundleID                string            `json:"bundleId"`
	Role                    string            `json:"role"`
	SupportedContentTypes   []string          `json:"supportedContentTypes,omitempty"`
	RequiredForContentTypes []string          `json:"requiredForContentTypes,omitempty"`
	SelectedFields          []string          `json:"selectedFields"`
	AssemblyMappings        []AssemblyMapping `json:"assemblyMappings"`
}

type AssemblyMapping struct {
	TargetField         string           `json:"targetField"`
	PresenceSourceField string           `json:"presenceSourceField,omitempty"`
	Sources             []AssemblySource `json:"sources"`
}

type AssemblySource struct {
	SourceField string `json:"sourceField"`
	Strategy    string `json:"strategy"`
	TargetKey   string `json:"targetKey,omitempty"`
}

func (bundle AppClientBundle) Validate() error {
	if !executorPattern.MatchString(bundle.BundleID) {
		return errors.New("bundleId is required and must be canonical")
	}
	if err := validateSortedBundleStrings("supportedContentTypes", bundle.SupportedContentTypes, contentTypePattern); err != nil {
		return err
	}
	if err := validateSortedBundleStrings("requiredForContentTypes", bundle.RequiredForContentTypes, contentTypePattern); err != nil {
		return err
	}
	if err := validateSortedBundleStrings("selectedFields", bundle.SelectedFields, graphQLName); err != nil {
		return err
	}
	if len(bundle.SelectedFields) == 0 {
		return errors.New("selectedFields must be non-empty")
	}
	if bundle.AssemblyMappings == nil {
		return errors.New("assemblyMappings is required, use an empty array when no mapping is needed")
	}
	switch bundle.Role {
	case "base":
		if len(bundle.SupportedContentTypes) == 0 || len(bundle.RequiredForContentTypes) != 0 {
			return errors.New("base requires supportedContentTypes and forbids requiredForContentTypes")
		}
	case "extension":
		if len(bundle.SupportedContentTypes) != 0 || len(bundle.RequiredForContentTypes) == 0 {
			return errors.New("extension requires non-empty requiredForContentTypes and forbids supportedContentTypes")
		}
	default:
		return fmt.Errorf("unsupported bundle role %q", bundle.Role)
	}
	for index, mapping := range bundle.AssemblyMappings {
		if index > 0 && bundle.AssemblyMappings[index-1].TargetField >= mapping.TargetField {
			return errors.New("assemblyMappings must be unique and sorted by targetField")
		}
		if !graphQLName.MatchString(mapping.TargetField) || len(mapping.Sources) == 0 {
			return fmt.Errorf("assembly target field %q is invalid or has no sources", mapping.TargetField)
		}
		mappingSources := map[string]bool{}
		assignKeys := map[string]bool{}
		for sourceIndex, source := range mapping.Sources {
			if sourceIndex > 0 && mapping.Sources[sourceIndex-1].SourceField >= source.SourceField {
				return fmt.Errorf("assembly sources for %s must be unique and sorted", mapping.TargetField)
			}
			if !graphQLName.MatchString(source.SourceField) {
				return fmt.Errorf("assembly source field %q is invalid", source.SourceField)
			}
			mappingSources[source.SourceField] = true
			switch source.Strategy {
			case "merge_object":
				if source.TargetKey != "" {
					return errors.New("merge_object forbids targetKey")
				}
			case "assign_key":
				if !graphQLName.MatchString(source.TargetKey) || assignKeys[source.TargetKey] {
					return errors.New("assign_key requires a unique GraphQL targetKey")
				}
				assignKeys[source.TargetKey] = true
			case "replace":
				if source.TargetKey != "" || len(mapping.Sources) != 1 {
					return errors.New("replace requires exactly one source and forbids targetKey")
				}
			default:
				return fmt.Errorf("unsupported assembly strategy %q", source.Strategy)
			}
		}
		if mapping.PresenceSourceField != "" && !mappingSources[mapping.PresenceSourceField] {
			return fmt.Errorf("presenceSourceField %s must reference a source in the same mapping", mapping.PresenceSourceField)
		}
	}
	return nil
}

func validateRegistryBundles(entries []Entry) error {
	groups := map[string][]Entry{}
	for _, entry := range entries {
		if entry.AppClientBundle == nil {
			continue
		}
		groups[entry.AppClientBundle.BundleID] = append(groups[entry.AppClientBundle.BundleID], entry)
	}
	for bundleID, group := range groups {
		if err := validateRegistryBundleGroup(bundleID, group); err != nil {
			return err
		}
	}
	return nil
}

func validateRegistryBundleGroup(bundleID string, entries []Entry) error {
	baseCount := 0
	var supported []string
	operations := map[string]bool{}
	allSelected := map[string]bool{}
	targets := map[string]bool{}
	consumedSources := map[string]bool{}
	for _, entry := range entries {
		bundle := entry.AppClientBundle
		if operations[entry.OperationName] {
			return fmt.Errorf("bundle %s has duplicate operationName %s", bundleID, entry.OperationName)
		}
		operations[entry.OperationName] = true
		if bundle.Role == "base" {
			baseCount++
			supported = bundle.SupportedContentTypes
			if !containsSorted(bundle.SelectedFields, "contentType") {
				return fmt.Errorf("bundle %s base must select contentType", bundleID)
			}
		}
		for _, field := range bundle.SelectedFields {
			allSelected[field] = true
		}
		for _, mapping := range bundle.AssemblyMappings {
			if targets[mapping.TargetField] {
				return fmt.Errorf("bundle %s assembly target %s is duplicated", bundleID, mapping.TargetField)
			}
			targets[mapping.TargetField] = true
			for _, source := range mapping.Sources {
				if !containsSorted(bundle.SelectedFields, source.SourceField) {
					return fmt.Errorf("bundle %s assembly source %s does not exist in its entry selectedFields", bundleID, source.SourceField)
				}
				if consumedSources[source.SourceField] {
					return fmt.Errorf("bundle %s assembly source %s is consumed more than once", bundleID, source.SourceField)
				}
				consumedSources[source.SourceField] = true
			}
		}
	}
	if baseCount != 1 {
		return fmt.Errorf("bundle %s requires exactly one base, got %d", bundleID, baseCount)
	}
	supportedSet := make(map[string]bool, len(supported))
	for _, contentType := range supported {
		supportedSet[contentType] = true
	}
	for _, entry := range entries {
		if entry.AppClientBundle.Role != "extension" {
			continue
		}
		for _, contentType := range entry.AppClientBundle.RequiredForContentTypes {
			if !supportedSet[contentType] {
				return fmt.Errorf("bundle %s extension %s content type %s is outside base supportedContentTypes", bundleID, entry.OperationName, contentType)
			}
		}
	}
	for target := range targets {
		if allSelected[target] {
			return fmt.Errorf("bundle %s assembly target %s conflicts with selectedFields", bundleID, target)
		}
	}
	return nil
}

func cloneAppClientBundle(source *AppClientBundle) *AppClientBundle {
	if source == nil {
		return nil
	}
	clone := &AppClientBundle{
		BundleID: source.BundleID, Role: source.Role,
		SupportedContentTypes:   append([]string(nil), source.SupportedContentTypes...),
		RequiredForContentTypes: append([]string(nil), source.RequiredForContentTypes...),
		SelectedFields:          append([]string(nil), source.SelectedFields...),
	}
	if source.AssemblyMappings != nil {
		clone.AssemblyMappings = make([]AssemblyMapping, len(source.AssemblyMappings))
		for index, mapping := range source.AssemblyMappings {
			clone.AssemblyMappings[index] = AssemblyMapping{
				TargetField: mapping.TargetField, PresenceSourceField: mapping.PresenceSourceField,
				Sources: append([]AssemblySource(nil), mapping.Sources...),
			}
		}
	}
	return clone
}

func validateSortedBundleStrings(name string, values []string, pattern *regexp.Regexp) error {
	for index, value := range values {
		if !pattern.MatchString(value) || index > 0 && values[index-1] >= value {
			return fmt.Errorf("%s must be non-empty, unique and sorted", name)
		}
	}
	return nil
}

func containsSorted(values []string, target string) bool {
	index := sort.SearchStrings(values, target)
	return index < len(values) && values[index] == target
}
