package main

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"time"
)

const tagImportReportSchema = "quwoquan.tag_import_report"

type releaseHeader struct {
	Schema      string `json:"schema"`
	ReleaseID   string `json:"releaseId"`
	ReleaseKind string `json:"releaseKind"`
}

type releaseDesiredState struct {
	Schema      string `json:"schema"`
	ReleaseID   string `json:"releaseId"`
	DesiredRefs struct {
		Tags []string `json:"tags"`
	} `json:"desiredRefs"`
}

type tagImportReport struct {
	Schema            string   `json:"schema"`
	Status            string   `json:"status"`
	Environment       string   `json:"environment"`
	ReleaseID         string   `json:"releaseId"`
	SourceOwner       string   `json:"sourceOwner"`
	CanonicalDigest   string   `json:"canonicalDigest"`
	ReleaseKind       string   `json:"releaseKind"`
	PreviousReleaseID string   `json:"previousReleaseId"`
	NodeCount         int      `json:"nodeCount"`
	TagRefs           []string `json:"tagRefs"`
	GeneratedAt       string   `json:"generatedAt"`
}

func collectReleaseTaxonomyNodes(releaseRoot string) (string, string, []taxonomyNode, error) {
	root, err := filepath.Abs(strings.TrimSpace(releaseRoot))
	if err != nil {
		return "", "", nil, fmt.Errorf("resolve release root: %w", err)
	}
	headerPath := filepath.Join(root, "payload", "release.json")
	headerRaw, err := os.ReadFile(headerPath)
	if err != nil {
		return "", "", nil, fmt.Errorf("read release header: %w", err)
	}
	var header releaseHeader
	if err := json.Unmarshal(headerRaw, &header); err != nil {
		return "", "", nil, fmt.Errorf("parse release header: %w", err)
	}
	if header.Schema != "quwoquan_data.release" ||
		strings.TrimSpace(header.ReleaseID) == "" ||
		(header.ReleaseKind != "content" && header.ReleaseKind != "empty_baseline") {
		return "", "", nil, fmt.Errorf("release header contract is invalid")
	}
	desiredPath := filepath.Join(root, "payload", "desired_state.json")
	raw, err := os.ReadFile(desiredPath)
	if err != nil {
		return "", "", nil, fmt.Errorf("read release desired state: %w", err)
	}
	var desired releaseDesiredState
	if err := json.Unmarshal(raw, &desired); err != nil {
		return "", "", nil, fmt.Errorf("parse release desired state: %w", err)
	}
	if desired.Schema != "quwoquan_data.release_desired_state" ||
		strings.TrimSpace(desired.ReleaseID) == "" ||
		desired.ReleaseID != header.ReleaseID {
		return "", "", nil, fmt.Errorf("release desired state contract is invalid")
	}
	tagsRoot := filepath.Join(root, "payload", "objects", "tags")
	seen := make(map[string]struct{}, len(desired.DesiredRefs.Tags))
	nodes := make([]taxonomyNode, 0, len(desired.DesiredRefs.Tags))
	for _, rawRef := range desired.DesiredRefs.Tags {
		tagRef := filepath.ToSlash(strings.TrimSpace(rawRef))
		if err := validateReleaseTagRef(tagRef); err != nil {
			return "", "", nil, err
		}
		if _, exists := seen[tagRef]; exists {
			return "", "", nil, fmt.Errorf("release desired tags contain duplicate %s", tagRef)
		}
		seen[tagRef] = struct{}{}
		path := filepath.Join(tagsRoot, filepath.FromSlash(tagRef), "_definition.json")
		definitionRaw, readErr := os.ReadFile(path)
		if readErr != nil {
			return "", "", nil, fmt.Errorf("read release tag snapshot %s: %w", tagRef, readErr)
		}
		var def definition
		if err := json.Unmarshal(definitionRaw, &def); err != nil {
			return "", "", nil, fmt.Errorf("parse release tag snapshot %s: %w", tagRef, err)
		}
		segments := strings.Split(tagRef, "/")
		parentTagRef := ""
		ancestors := make([]string, 0, len(segments)-1)
		if len(segments) > 1 {
			parentTagRef = strings.Join(segments[:len(segments)-1], "/")
			for index := 1; index < len(segments); index++ {
				ancestors = append(ancestors, strings.Join(segments[:index], "/"))
			}
		}
		nodes = append(nodes, taxonomyNode{
			tagRef:       tagRef,
			group:        segments[0],
			nodeKind:     "definition",
			label:        firstNonEmpty(def.Label, def.DisplayName, segments[len(segments)-1]),
			labelEn:      def.LabelEn,
			description:  firstNonEmpty(def.Description, def.Semantics),
			aliases:      normalizedStrings(def.Aliases),
			parentTagRef: parentTagRef,
			ancestors:    ancestors,
			depth:        len(segments) - 1,
			maxDepth:     def.MaxDepth,
			pathPolicy:   strings.TrimSpace(def.PathPolicy),
		})
	}
	var actual []string
	if tagsInfo, statErr := os.Stat(tagsRoot); statErr == nil && tagsInfo.IsDir() {
		if err := filepath.WalkDir(tagsRoot, func(path string, entry os.DirEntry, walkErr error) error {
			if walkErr != nil {
				return walkErr
			}
			if entry.IsDir() || entry.Name() != "_definition.json" {
				return nil
			}
			relative, relErr := filepath.Rel(tagsRoot, filepath.Dir(path))
			if relErr != nil {
				return relErr
			}
			actual = append(actual, filepath.ToSlash(relative))
			return nil
		}); err != nil {
			return "", "", nil, fmt.Errorf("scan release tag snapshots: %w", err)
		}
	} else if statErr != nil && !os.IsNotExist(statErr) {
		return "", "", nil, fmt.Errorf("stat release tag snapshots: %w", statErr)
	}
	sort.Strings(actual)
	expected := append([]string(nil), desired.DesiredRefs.Tags...)
	sort.Strings(expected)
	if strings.Join(actual, "\x00") != strings.Join(expected, "\x00") {
		return "", "", nil, fmt.Errorf("release tag snapshot closure differs from desired state")
	}
	sort.Slice(nodes, func(left, right int) bool {
		return nodes[left].tagRef < nodes[right].tagRef
	})
	if err := validateReleaseTaxonomyNodes(header.ReleaseKind, nodes); err != nil {
		return "", "", nil, err
	}
	return desired.ReleaseID, header.ReleaseKind, nodes, nil
}

func validateReleaseTagRef(tagRef string) error {
	if tagRef == "" || strings.HasPrefix(tagRef, "/") {
		return fmt.Errorf("release tagRef is invalid: %q", tagRef)
	}
	segments := strings.Split(tagRef, "/")
	if len(segments) < 2 || !validGroups[segments[0]] {
		return fmt.Errorf("release tagRef has invalid group: %s", tagRef)
	}
	for _, segment := range segments {
		if segment == "" || segment == "." || segment == ".." {
			return fmt.Errorf("release tagRef has unsafe segment: %s", tagRef)
		}
	}
	return nil
}

func validateReleaseTaxonomyNodes(releaseKind string, nodes []taxonomyNode) error {
	if releaseKind == "content" && len(nodes) == 0 {
		return fmt.Errorf("content release contains no tag snapshots")
	}
	if releaseKind == "empty_baseline" && len(nodes) != 0 {
		return fmt.Errorf("empty baseline release must contain zero tag snapshots")
	}
	for _, node := range nodes {
		if strings.TrimSpace(node.label) == "" {
			return fmt.Errorf("release tag snapshot %s has no label", node.tagRef)
		}
	}
	return nil
}

func writeTagImportReport(path string, report tagImportReport) error {
	if strings.TrimSpace(path) == "" {
		return fmt.Errorf("report path is required")
	}
	report.GeneratedAt = time.Now().UTC().Format(time.RFC3339Nano)
	payload, err := json.MarshalIndent(report, "", "  ")
	if err != nil {
		return err
	}
	payload = append(payload, '\n')
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		return err
	}
	return os.WriteFile(path, payload, 0o644)
}

func tagRefs(nodes []taxonomyNode) []string {
	refs := make([]string, 0, len(nodes))
	for _, node := range nodes {
		refs = append(refs, node.tagRef)
	}
	return refs
}
