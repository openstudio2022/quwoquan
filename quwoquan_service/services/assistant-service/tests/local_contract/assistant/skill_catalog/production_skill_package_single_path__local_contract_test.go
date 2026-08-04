// spec_ref: specs/feature-tree/assistant-run-learning/skill-product-integration-platform/active-skill-package-catalog/spec.md#gwt-001
package local_contract

import (
	"fmt"
	"go/parser"
	"go/token"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"testing"

	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/orchestration"
	assistant "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain/model"
	skillpkg "quwoquan_service/services/assistant-service/internal/assistant/skill_package_release/application/packageasset"
)

const assistantServiceImportPrefix = "quwoquan_service/services/assistant-service"

func TestAssistantAPIBinaryUsesOnlyImmutableSkillPackageConsumers(t *testing.T) {
	root := assistantServiceRoot(t)
	reachable, err := assistantServicePackageGraph(root, "cmd/api")
	if err != nil {
		t.Fatalf("resolve assistant API import graph: %v", err)
	}

	for _, required := range []string{
		"internal/assistant/skill_catalog/infrastructure/activerelease",
		"internal/assistant/skill_package_release/application",
		"internal/assistant/skill_package_release/infrastructure/artifact",
	} {
		if !reachable[required] {
			t.Fatalf("assistant API does not reach immutable package owner %q", required)
		}
	}
	for _, forbidden := range []string{
		"internal/assistant/skill_catalog/infrastructure/resource",
		"internal/assistant/assistant_session/infrastructure/assets",
		"internal/assistant/assistant_run/application/replay",
	} {
		if reachable[forbidden] {
			t.Fatalf("assistant API reaches source/test Skill package reader %q", forbidden)
		}
	}

	assertRuntimeSkillSourceHasNoFallbackLoader(t, root)
}

func TestRuntimeDoesNotInventCatalogWhenPackageConsumerIsMissing(t *testing.T) {
	turn := assistant.AssistantTurn{
		TurnID: "turn-no-package",
		Input:  assistant.AssistantTurnInput{Text: "杭州旅行计划"},
	}
	if routed := skillpkg.NewRouter(nil).Route(turn); routed.SkillID != "" {
		t.Fatalf("empty package catalog invented Skill %q", routed.SkillID)
	}
	if _, err := (orchestration.DefaultSkillRuntime{}).SelectSkill(
		t.Context(),
		turn,
	); err != skillpkg.ErrCatalogUnavailable {
		t.Fatalf("missing package consumer error=%v, want %v", err, skillpkg.ErrCatalogUnavailable)
	}
	if _, err := (orchestration.ManifestSkillRuntime{}).SelectSkill(
		t.Context(),
		turn,
	); err != skillpkg.ErrCatalogUnavailable {
		t.Fatalf("missing manifest loader error=%v, want %v", err, skillpkg.ErrCatalogUnavailable)
	}
}

func assistantServicePackageGraph(
	root string,
	entry string,
) (map[string]bool, error) {
	queue := []string{filepath.Clean(entry)}
	visited := map[string]bool{}
	for len(queue) > 0 {
		current := queue[0]
		queue = queue[1:]
		if visited[current] {
			continue
		}
		visited[current] = true

		imports, err := assistantServiceImports(filepath.Join(root, current))
		if err != nil {
			return nil, fmt.Errorf("parse package %s: %w", current, err)
		}
		for _, imported := range imports {
			if imported == assistantServiceImportPrefix {
				queue = append(queue, ".")
				continue
			}
			prefix := assistantServiceImportPrefix + "/"
			if strings.HasPrefix(imported, prefix) {
				queue = append(queue, filepath.FromSlash(strings.TrimPrefix(imported, prefix)))
			}
		}
	}
	return visited, nil
}

func assistantServiceImports(directory string) ([]string, error) {
	entries, err := os.ReadDir(directory)
	if err != nil {
		return nil, err
	}
	imports := []string{}
	for _, entry := range entries {
		if entry.IsDir() || !strings.HasSuffix(entry.Name(), ".go") ||
			strings.HasSuffix(entry.Name(), "_test.go") {
			continue
		}
		file, err := parser.ParseFile(
			token.NewFileSet(),
			filepath.Join(directory, entry.Name()),
			nil,
			parser.ImportsOnly,
		)
		if err != nil {
			return nil, err
		}
		for _, imported := range file.Imports {
			path, err := strconv.Unquote(imported.Path.Value)
			if err != nil {
				return nil, err
			}
			imports = append(imports, path)
		}
	}
	return imports, nil
}

func assertRuntimeSkillSourceHasNoFallbackLoader(t *testing.T, root string) {
	t.Helper()
	runtimeRoot := filepath.Join(
		root,
		"internal",
		"assistant",
		"assistant_session",
	)
	forbidden := []string{
		"type JSONFileLoader",
		"func DefaultManifest(",
		"type StaticLoader",
		"NewDefaultPromptAssetLoader",
		"fallback_general_search",
	}
	err := filepath.WalkDir(runtimeRoot, func(path string, entry os.DirEntry, err error) error {
		if err != nil {
			return err
		}
		if entry.IsDir() || !strings.HasSuffix(path, ".go") ||
			strings.HasSuffix(path, "_test.go") {
			return nil
		}
		raw, err := os.ReadFile(path)
		if err != nil {
			return err
		}
		for _, marker := range forbidden {
			if strings.Contains(string(raw), marker) {
				return fmt.Errorf("%s retains forbidden Skill source fallback %q", path, marker)
			}
		}
		return nil
	})
	if err != nil {
		t.Fatal(err)
	}
}
