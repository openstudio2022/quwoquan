package importmanifest

import (
	"bytes"
	"encoding/json"
	"fmt"
	"sort"
	"strings"
)

// Entry is one canonical object-to-tag projection row accepted by the data
// import command.
type Entry struct {
	ObjectID   string   `json:"objectId"`
	ObjectType string   `json:"objectType"`
	TagRefs    []string `json:"tagRefs"`
}

type envelope struct {
	ObjectTagIndex []Entry `json:"object_tag_index"`
}

var allowedObjectTypes = map[string]struct{}{
	"post":   {},
	"circle": {},
	"entity": {},
	"user":   {},
}

var allowedTagPrefixes = []string{
	"Topic/",
	"Entity/",
	"Audience/",
	"Format/",
}

// Decode accepts only a flat array or immutable-release manifest from Data
// Engineering. Environment seed sets are intentionally unsupported.
func Decode(raw []byte) ([]Entry, error) {
	trimmed := bytes.TrimSpace(raw)
	if len(trimmed) == 0 {
		return nil, fmt.Errorf("object tag manifest is empty")
	}

	if trimmed[0] == '[' {
		var entries []Entry
		if err := json.Unmarshal(trimmed, &entries); err != nil {
			return nil, fmt.Errorf("decode object tag array: %w", err)
		}
		return validateEntries(entries)
	}

	var manifest envelope
	if err := json.Unmarshal(trimmed, &manifest); err != nil {
		return nil, fmt.Errorf("decode object tag manifest: %w", err)
	}
	if len(manifest.ObjectTagIndex) > 0 {
		return validateEntries(manifest.ObjectTagIndex)
	}
	return nil, fmt.Errorf("object tag manifest contains no importable entries")
}

func validateEntries(entries []Entry) ([]Entry, error) {
	if len(entries) == 0 {
		return nil, fmt.Errorf("object tag manifest contains no entries")
	}
	seenObjects := make(map[string]struct{}, len(entries))
	normalized := make([]Entry, 0, len(entries))
	for index, entry := range entries {
		objectID := strings.TrimSpace(entry.ObjectID)
		objectType := strings.TrimSpace(entry.ObjectType)
		if objectID == "" || objectType == "" {
			return nil, fmt.Errorf("object tag entry %d has incomplete identity", index)
		}
		if _, ok := allowedObjectTypes[objectType]; !ok {
			return nil, fmt.Errorf("object tag entry %d has unsupported objectType %q", index, objectType)
		}
		identity := objectType + "\x00" + objectID
		if _, exists := seenObjects[identity]; exists {
			return nil, fmt.Errorf("object tag identity %s/%s is duplicated", objectType, objectID)
		}
		seenObjects[identity] = struct{}{}

		tagRefs, err := normalizeTagRefs(entry.TagRefs)
		if err != nil {
			return nil, fmt.Errorf("object tag entry %d: %w", index, err)
		}
		normalized = append(normalized, Entry{
			ObjectID:   objectID,
			ObjectType: objectType,
			TagRefs:    tagRefs,
		})
	}
	return normalized, nil
}

func normalizeTagRefs(tagRefs []string) ([]string, error) {
	if len(tagRefs) == 0 {
		return nil, fmt.Errorf("tagRefs must not be empty")
	}
	seen := make(map[string]struct{}, len(tagRefs))
	normalized := make([]string, 0, len(tagRefs))
	for _, raw := range tagRefs {
		tagRef := strings.TrimSpace(raw)
		if !hasAllowedTagPrefix(tagRef) {
			return nil, fmt.Errorf("tagRef %q is outside the canonical taxonomy", tagRef)
		}
		if _, exists := seen[tagRef]; exists {
			continue
		}
		seen[tagRef] = struct{}{}
		normalized = append(normalized, tagRef)
	}
	sort.Strings(normalized)
	return normalized, nil
}

func hasAllowedTagPrefix(tagRef string) bool {
	for _, prefix := range allowedTagPrefixes {
		if strings.HasPrefix(tagRef, prefix) {
			return true
		}
	}
	return false
}
