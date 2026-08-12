package main

import (
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strings"
)

var (
	digestPattern    = regexp.MustCompile(`^sha256:[0-9a-f]{64}$`)
	operationPattern = regexp.MustCompile(`^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*\.[A-Z][A-Za-z0-9]*$`)
	objectIDPattern  = regexp.MustCompile(`^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$`)
	executorPattern  = regexp.MustCompile(`^[a-z][A-Za-z0-9]*(\.[a-zA-Z][A-Za-z0-9]*)+$`)
	graphQLName      = regexp.MustCompile(`^[_A-Za-z][_0-9A-Za-z]*$`)
)

const (
	maximumOwnerCalls    = 64
	maximumBatchKeys     = 10_000
	maximumResponseBytes = 4 * 1024 * 1024
)

func loadMetadata(path string) (metadataFile, error) {
	file, err := openRegular(path, "query metadata")
	if err != nil {
		return metadataFile{}, err
	}
	defer file.Close()
	decoder := json.NewDecoder(file)
	decoder.DisallowUnknownFields()
	var metadata metadataFile
	if err := decoder.Decode(&metadata); err != nil {
		return metadataFile{}, fmt.Errorf("decode query metadata: %w", err)
	}
	var trailing any
	if err := decoder.Decode(&trailing); !errors.Is(err, io.EOF) {
		return metadataFile{}, errors.New("query metadata must contain one JSON object")
	}
	if metadata.Schema != metadataSchema {
		return metadataFile{}, fmt.Errorf("query metadata schema=%q", metadata.Schema)
	}
	if len(metadata.Entries) == 0 {
		return metadataFile{}, errors.New("query metadata must contain entries")
	}
	seenDocuments := map[string]struct{}{}
	seenOperations := map[string]struct{}{}
	for index := range metadata.Entries {
		entry := &metadata.Entries[index]
		if err := validateMetadataEntry(entry); err != nil {
			return metadataFile{}, fmt.Errorf("query metadata entry %d: %w", index, err)
		}
		if _, exists := seenDocuments[entry.Document]; exists {
			return metadataFile{}, fmt.Errorf("duplicate query document %q", entry.Document)
		}
		seenDocuments[entry.Document] = struct{}{}
		if _, exists := seenOperations[entry.CanonicalOperationID]; exists {
			return metadataFile{}, fmt.Errorf("duplicate canonicalOperationId %q", entry.CanonicalOperationID)
		}
		seenOperations[entry.CanonicalOperationID] = struct{}{}
	}
	return metadata, nil
}

func validateMetadataEntry(entry *metadataEntry) error {
	entry.Document = strings.TrimSpace(entry.Document)
	if entry.Document == "" {
		return errors.New("document is required")
	}
	document := filepath.Clean(filepath.FromSlash(entry.Document))
	if filepath.IsAbs(document) || document == "." || document == ".." || strings.HasPrefix(document, ".."+string(filepath.Separator)) {
		return errors.New("document must stay relative to the metadata directory")
	}
	entry.Document = filepath.ToSlash(document)
	if !operationPattern.MatchString(entry.CanonicalOperationID) {
		return fmt.Errorf("canonicalOperationId=%q is invalid", entry.CanonicalOperationID)
	}
	if _, ok := queryClassComplexityLimit(entry.QueryClass); !ok {
		return fmt.Errorf("queryClass=%q is invalid", entry.QueryClass)
	}
	if entry.VariablesMaxBytes < 1 || entry.VariablesMaxBytes > 64*1024 {
		return errors.New("variablesMaxBytes must be within 1..65536")
	}
	if entry.MaxOwnerCalls < 1 || entry.MaxOwnerCalls > maximumOwnerCalls {
		return fmt.Errorf("maxOwnerCalls must be within 1..%d", maximumOwnerCalls)
	}
	if entry.MaxBatchKeys < 1 || entry.MaxBatchKeys > maximumBatchKeys {
		return fmt.Errorf("maxBatchKeys must be within 1..%d", maximumBatchKeys)
	}
	if entry.MaxResponseBytes < 1 || entry.MaxResponseBytes > maximumResponseBytes {
		return fmt.Errorf("maxResponseBytes must be within 1..%d", maximumResponseBytes)
	}
	var err error
	if entry.SLORef, err = normalizeGovernanceRef("sloRef", entry.SLORef, true); err != nil {
		return err
	}
	if entry.DepthExceptionRef, err = normalizeGovernanceRef("depthExceptionRef", entry.DepthExceptionRef, false); err != nil {
		return err
	}
	if entry.TopLevelExceptionRef, err = normalizeGovernanceRef("topLevelExceptionRef", entry.TopLevelExceptionRef, false); err != nil {
		return err
	}
	if entry.ComplexityExceptionRef, err = normalizeGovernanceRef("complexityExceptionRef", entry.ComplexityExceptionRef, false); err != nil {
		return err
	}
	if !executorPattern.MatchString(entry.ExecutorKey) {
		return fmt.Errorf("executorKey=%q is invalid", entry.ExecutorKey)
	}
	return nil
}

func normalizeGovernanceRef(name, value string, required bool) (string, error) {
	value = strings.TrimSpace(value)
	if value == "" {
		if required {
			return "", fmt.Errorf("%s is required", name)
		}
		return "", nil
	}
	if len(value) > 512 || strings.ContainsAny(value, "\r\n\t ") || !strings.Contains(value, ":") {
		return "", fmt.Errorf("%s must be a typed reference without whitespace", name)
	}
	return value, nil
}

func validateAuthorization(binding *authorizationMetadata) error {
	allowed := map[string]struct{}{
		"public": {}, "account": {}, "persona": {}, "device": {},
		"service": {}, "operator": {}, "admin": {},
	}
	if _, ok := allowed[binding.Principal]; !ok {
		return fmt.Errorf("authorization principal=%q is invalid", binding.Principal)
	}
	if strings.TrimSpace(binding.OwnershipPolicy) == "" {
		return errors.New("authorization ownershipPolicy is required")
	}
	if err := validateSortedStrings("authorization scopes", binding.Scopes, nil); err != nil {
		return err
	}
	for _, scope := range binding.Scopes {
		if strings.TrimSpace(scope) == "" {
			return errors.New("authorization scopes must not contain blanks")
		}
	}
	return nil
}

func validateSortedStrings(label string, values []string, pattern *regexp.Regexp) error {
	if !sort.StringsAreSorted(values) {
		return fmt.Errorf("%s must be sorted", label)
	}
	for index, value := range values {
		if index > 0 && value == values[index-1] {
			return fmt.Errorf("%s contains duplicate %q", label, value)
		}
		if pattern != nil && !pattern.MatchString(value) {
			return fmt.Errorf("%s contains invalid value %q", label, value)
		}
	}
	return nil
}

func openRegular(path string, label string) (*os.File, error) {
	info, err := os.Lstat(path)
	if err != nil {
		return nil, fmt.Errorf("%s is unavailable: %w", label, err)
	}
	if !info.Mode().IsRegular() {
		return nil, fmt.Errorf("%s must be a regular file", label)
	}
	file, err := os.Open(path)
	if err != nil {
		return nil, fmt.Errorf("open %s: %w", label, err)
	}
	return file, nil
}

func queryClassComplexityLimit(class string) (int, bool) {
	switch class {
	case "detail":
		return 100, true
	case "collection":
		return 300, true
	case "page_composite":
		return 500, true
	default:
		return 0, false
	}
}
