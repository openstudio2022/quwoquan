package importmanifest

import (
	"bytes"
	"encoding/json"
	"fmt"
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
	SeedSets       map[string]json.RawMessage `json:"seedSets"`
	ObjectTagIndex []Entry                    `json:"object_tag_index"`
}

type seedBlock struct {
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

// Decode accepts either a flat array/manifest from the data pipeline or
// explicitly selected seed sets from an environment seed manifest. Seed-set
// input is fail-closed: callers must name every selected ref, and undeclared
// blocks are never imported implicitly.
func Decode(raw []byte, seedRefs []string) ([]Entry, error) {
	trimmed := bytes.TrimSpace(raw)
	if len(trimmed) == 0 {
		return nil, fmt.Errorf("object tag manifest is empty")
	}

	if trimmed[0] == '[' {
		if len(seedRefs) > 0 {
			return nil, fmt.Errorf("seed refs are only valid for a seed-set manifest")
		}
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
	hasFlatEntries := len(manifest.ObjectTagIndex) > 0
	hasSeedSets := len(manifest.SeedSets) > 0
	if hasFlatEntries && hasSeedSets {
		return nil, fmt.Errorf("object tag manifest cannot mix flat entries and seed sets")
	}
	if hasFlatEntries {
		if len(seedRefs) > 0 {
			return nil, fmt.Errorf("seed refs are only valid for a seed-set manifest")
		}
		return validateEntries(manifest.ObjectTagIndex)
	}
	if !hasSeedSets {
		return nil, fmt.Errorf("object tag manifest contains no importable entries")
	}

	refs, err := normalizeSeedRefs(seedRefs)
	if err != nil {
		return nil, err
	}
	entries := make([]Entry, 0)
	for _, ref := range refs {
		rawBlock, ok := manifest.SeedSets[ref]
		if !ok {
			return nil, fmt.Errorf("object tag seed ref %q does not exist", ref)
		}
		var block seedBlock
		if err := json.Unmarshal(rawBlock, &block); err != nil {
			return nil, fmt.Errorf("decode object tag seed ref %q: %w", ref, err)
		}
		entries = append(entries, block.ObjectTagIndex...)
	}
	return validateEntries(entries)
}

func normalizeSeedRefs(seedRefs []string) ([]string, error) {
	if len(seedRefs) == 0 {
		return nil, fmt.Errorf("seed-set manifest requires explicit seed refs")
	}
	seen := make(map[string]struct{}, len(seedRefs))
	normalized := make([]string, 0, len(seedRefs))
	for _, raw := range seedRefs {
		ref := strings.TrimSpace(raw)
		if ref == "" {
			return nil, fmt.Errorf("object tag seed ref must not be empty")
		}
		if _, exists := seen[ref]; exists {
			return nil, fmt.Errorf("object tag seed ref %q is duplicated", ref)
		}
		seen[ref] = struct{}{}
		normalized = append(normalized, ref)
	}
	return normalized, nil
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
