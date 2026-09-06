package main

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"time"

	"quwoquan_service/runtime/datarelease"
	"quwoquan_service/services/tag-service/internal/tag/tag_node_view/domain/lifecycle"
)

const tagImportReportSchema = "quwoquan.tag_import_report"

type contentReleaseBinding struct {
	ReleaseID      string
	SourceOwner    string
	ReleaseKind    string
	ManifestDigest string
}

type releaseDesiredState struct {
	Schema      string `json:"schema"`
	ReleaseID   string `json:"releaseId"`
	DesiredRefs struct {
		Tags []string `json:"tags"`
	} `json:"desiredRefs"`
}

type tagImportReport struct {
	Schema          string   `json:"schema"`
	Status          string   `json:"status"`
	Environment     string   `json:"environment"`
	ReleaseID       string   `json:"releaseId"`
	SourceOwner     string   `json:"sourceOwner"`
	ManifestDigest  string   `json:"manifestDigest"`
	ActivationMode  string   `json:"activationMode"`
	CanonicalDigest string   `json:"canonicalDigest"`
	ReleaseKind     string   `json:"releaseKind"`
	NodeCount       int      `json:"nodeCount"`
	TagRefs         []string `json:"tagRefs"`
	GeneratedAt     string   `json:"generatedAt"`
}

func collectReleaseTaxonomyNodes(releaseRoot string) (contentReleaseBinding, []taxonomyNode, error) {
	tuple, err := datarelease.Load(strings.TrimSpace(releaseRoot))
	if err != nil {
		return contentReleaseBinding{}, nil, fmt.Errorf("load canonical Data release: %w", err)
	}
	root, err := filepath.Abs(strings.TrimSpace(releaseRoot))
	if err != nil {
		return contentReleaseBinding{}, nil, fmt.Errorf("resolve release root: %w", err)
	}
	header := contentReleaseBinding{
		ReleaseID: tuple.ReleaseID, SourceOwner: string(tuple.SourceOwner),
		ReleaseKind: string(tuple.ReleaseKind), ManifestDigest: string(tuple.PayloadSHA256),
	}
	desiredPath := filepath.Join(root, "payload", "desired_state.json")
	raw, err := os.ReadFile(desiredPath)
	if err != nil {
		return contentReleaseBinding{}, nil, fmt.Errorf("read release desired state: %w", err)
	}
	var desired releaseDesiredState
	if err := json.Unmarshal(raw, &desired); err != nil {
		return contentReleaseBinding{}, nil, fmt.Errorf("parse release desired state: %w", err)
	}
	if desired.Schema != "quwoquan_data.release_desired_state" ||
		strings.TrimSpace(desired.ReleaseID) == "" ||
		desired.ReleaseID != header.ReleaseID {
		return contentReleaseBinding{}, nil, fmt.Errorf("release desired state contract is invalid")
	}
	tagsRoot := filepath.Join(root, "payload", "objects", "tags")
	seen := make(map[string]struct{}, len(desired.DesiredRefs.Tags))
	nodes := make([]taxonomyNode, 0, len(desired.DesiredRefs.Tags))
	for _, rawRef := range desired.DesiredRefs.Tags {
		tagRef := filepath.ToSlash(strings.TrimSpace(rawRef))
		if err := validateReleaseTagRef(tagRef); err != nil {
			return contentReleaseBinding{}, nil, err
		}
		if _, exists := seen[tagRef]; exists {
			return contentReleaseBinding{}, nil, fmt.Errorf("release desired tags contain duplicate %s", tagRef)
		}
		seen[tagRef] = struct{}{}
		path := filepath.Join(tagsRoot, filepath.FromSlash(tagRef), "_definition.json")
		definitionRaw, readErr := os.ReadFile(path)
		if readErr != nil {
			return contentReleaseBinding{}, nil, fmt.Errorf("read release tag snapshot %s: %w", tagRef, readErr)
		}
		var def definition
		if err := json.Unmarshal(definitionRaw, &def); err != nil {
			return contentReleaseBinding{}, nil, fmt.Errorf("parse release tag snapshot %s: %w", tagRef, err)
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
		lifecycleStatus, heatWindow, lifecycleErr := lifecycle.ResolveDeclaration(
			def.LifecycleStatus,
			def.HeatWindow,
		)
		if lifecycleErr != nil {
			return contentReleaseBinding{}, nil, fmt.Errorf(
				"release tag snapshot %s: %w",
				tagRef,
				lifecycleErr,
			)
		}
		nodes = append(nodes, taxonomyNode{
			tagRef:          tagRef,
			group:           segments[0],
			nodeKind:        "definition",
			label:           firstNonEmpty(def.Label, def.DisplayName, segments[len(segments)-1]),
			labelEn:         def.LabelEn,
			description:     firstNonEmpty(def.Description, def.Semantics),
			aliases:         normalizedStrings(def.Aliases),
			axisRole:        strings.TrimSpace(def.AxisRole),
			sameAsRefs:      normalizedStrings(def.SameAsRefs),
			parentTagRef:    parentTagRef,
			ancestors:       ancestors,
			depth:           len(segments) - 1,
			maxDepth:        def.MaxDepth,
			pathPolicy:      strings.TrimSpace(def.PathPolicy),
			lifecycleStatus: string(lifecycleStatus),
			heatWindow:      heatWindow,
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
			return contentReleaseBinding{}, nil, fmt.Errorf("scan release tag snapshots: %w", err)
		}
	} else if statErr != nil && !os.IsNotExist(statErr) {
		return contentReleaseBinding{}, nil, fmt.Errorf("stat release tag snapshots: %w", statErr)
	}
	sort.Strings(actual)
	expected := append([]string(nil), desired.DesiredRefs.Tags...)
	sort.Strings(expected)
	if strings.Join(actual, "\x00") != strings.Join(expected, "\x00") {
		return contentReleaseBinding{}, nil, fmt.Errorf("release tag snapshot closure differs from desired state")
	}
	sort.Slice(nodes, func(left, right int) bool {
		return nodes[left].tagRef < nodes[right].tagRef
	})
	if err := validateReleaseTaxonomyNodes(header.ReleaseKind, nodes); err != nil {
		return contentReleaseBinding{}, nil, err
	}
	return header, nodes, nil
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
