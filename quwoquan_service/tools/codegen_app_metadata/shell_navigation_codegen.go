package main

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"reflect"
	"sort"
	"strings"
)

const (
	shellNavigationGenerator = "tools/codegen_app_metadata"
	shellNavigationOwner     = "app-shell-navigation-emitter"
	shellNavigationMode      = "shell-navigation-metadata-only"
)

var shellNavigationMetadataPaths = []string{
	"_shared/app_routes.yaml",
	"_shared/app_pages.yaml",
	"_shared/ui_surfaces.yaml",
	"_shared/link_templates.yaml",
}

var shellNavigationOutputNames = []string{
	"app_pages.g.dart",
	"app_route_paths.g.dart",
	"app_ui_surfaces.g.dart",
	"link_templates.g.dart",
	"page_access_internal_routes.g.dart",
}

type shellNavigationInput struct {
	Path   string `json:"path"`
	SHA256 string `json:"sha256"`
}

type shellNavigationOutput struct {
	Path      string `json:"path"`
	Owner     string `json:"owner"`
	Generator string `json:"generator"`
	SHA256    string `json:"sha256"`
	Bytes     int    `json:"bytes"`
}

type shellNavigationManifest struct {
	Generator      string                  `json:"generator"`
	Responsibility string                  `json:"responsibility"`
	MetadataSHA256 string                  `json:"metadataSha256"`
	Inputs         []shellNavigationInput  `json:"inputs"`
	Outputs        []shellNavigationOutput `json:"outputs"`
}

type shellNavigationDocuments struct {
	routes        *appRoutesFile
	pages         *appPagesFile
	surfaces      *uiSurfacesFile
	linkTemplates *linkTemplatesFile
}

type shellNavigationArtifact struct {
	relativePath string
	content      []byte
}

func runShellNavigationMetadataMode(
	metadataDir string,
	appDir string,
	manifestPath string,
	check bool,
) error {
	if err := initializeMetadataDocumentSource(
		metadataDir,
		shellNavigationMetadataPaths,
	); err != nil {
		return fmt.Errorf("initialize shell navigation metadata source: %w", err)
	}
	documents, err := readShellNavigationDocuments(metadataDir)
	if err != nil {
		return err
	}
	if err := validateShellNavigationDocuments(documents); err != nil {
		return err
	}
	artifacts := renderShellNavigationArtifacts(appDir, documents)
	manifest, err := buildShellNavigationManifest(artifacts)
	if err != nil {
		return err
	}
	if strings.TrimSpace(manifestPath) == "" {
		manifestPath = filepath.Join(
			appDir,
			"tool",
			"shell_navigation_codegen",
			"generated_manifest.json",
		)
	}
	if check {
		return checkShellNavigationArtifacts(appDir, manifestPath, artifacts, manifest)
	}
	return writeShellNavigationArtifacts(appDir, manifestPath, artifacts, manifest)
}

func readShellNavigationDocuments(
	metadataDir string,
) (*shellNavigationDocuments, error) {
	routes, err := readAppRoutes(
		filepath.Join(metadataDir, "_shared", "app_routes.yaml"),
	)
	if err != nil {
		return nil, fmt.Errorf("read shell navigation app routes: %w", err)
	}
	pages, err := readAppPages(
		filepath.Join(metadataDir, "_shared", "app_pages.yaml"),
	)
	if err != nil {
		return nil, fmt.Errorf("read shell navigation app pages: %w", err)
	}
	surfaces, err := readUISurfaces(
		filepath.Join(metadataDir, "_shared", "ui_surfaces.yaml"),
	)
	if err != nil {
		return nil, fmt.Errorf("read shell navigation UI surfaces: %w", err)
	}
	linkTemplates, err := readLinkTemplates(
		filepath.Join(metadataDir, "_shared", "link_templates.yaml"),
	)
	if err != nil {
		return nil, fmt.Errorf("read shell navigation link templates: %w", err)
	}
	return &shellNavigationDocuments{
		routes:        routes,
		pages:         pages,
		surfaces:      surfaces,
		linkTemplates: linkTemplates,
	}, nil
}

func validateShellNavigationDocuments(
	documents *shellNavigationDocuments,
) error {
	if documents == nil ||
		documents.routes == nil ||
		documents.pages == nil ||
		documents.surfaces == nil ||
		documents.linkTemplates == nil {
		return fmt.Errorf("shell navigation metadata documents are incomplete")
	}
	routes := make(map[string]string, len(documents.routes.Routes))
	routePaths := make(map[string]string, len(documents.routes.Routes))
	for _, route := range documents.routes.Routes {
		id := strings.TrimSpace(route.ID)
		path := strings.TrimSpace(route.Path)
		if id == "" || path == "" {
			return fmt.Errorf("shell navigation route requires id and path")
		}
		if _, exists := routes[id]; exists {
			return fmt.Errorf("duplicate shell navigation route id %q", id)
		}
		if previous, exists := routePaths[path]; exists {
			return fmt.Errorf(
				"duplicate shell navigation route path %q for %s and %s",
				path,
				previous,
				id,
			)
		}
		routes[id] = path
		routePaths[path] = id
	}

	pageRoutes := map[string]struct{}{}
	for _, page := range documents.pages.Pages {
		pageName := strings.TrimSpace(page.PageName)
		routeID := strings.TrimSpace(page.RouteID)
		if pageName == "" || routeID == "" {
			return fmt.Errorf("shell navigation page requires page_name and route_id")
		}
		if _, exists := pageRoutes[routeID]; exists {
			return fmt.Errorf("duplicate shell navigation page route_id %q", routeID)
		}
		if _, exists := routes[routeID]; !exists {
			return fmt.Errorf(
				"shell navigation page %q references unknown route %q",
				pageName,
				routeID,
			)
		}
		pageRoutes[routeID] = struct{}{}
	}

	internalIDs := map[string]struct{}{}
	internalLocations := map[string]struct{}{}
	for _, page := range documents.pages.InternalPages {
		pageName := strings.TrimSpace(page.PageName)
		internalID := strings.TrimSpace(page.InternalID)
		location := strings.TrimSpace(page.Location)
		if pageName == "" || internalID == "" || location == "" {
			return fmt.Errorf(
				"shell internal page requires page_name, internal_id, and location",
			)
		}
		if _, exists := internalIDs[internalID]; exists {
			return fmt.Errorf("duplicate shell internal page id %q", internalID)
		}
		if _, exists := internalLocations[location]; exists {
			return fmt.Errorf(
				"duplicate shell internal page location %q",
				location,
			)
		}
		internalIDs[internalID] = struct{}{}
		internalLocations[location] = struct{}{}
	}

	surfaceIDs := map[string]struct{}{}
	for _, surface := range documents.surfaces.Surfaces {
		id := strings.TrimSpace(surface.ID)
		routeID := strings.TrimSpace(surface.RouteID)
		pathTemplate := strings.TrimSpace(surface.PathTemplate)
		if id == "" || routeID == "" || pathTemplate == "" {
			return fmt.Errorf(
				"shell UI surface requires id, route_id, and path_template",
			)
		}
		if _, exists := surfaceIDs[id]; exists {
			return fmt.Errorf("duplicate shell UI surface id %q", id)
		}
		routePath, exists := routes[routeID]
		if !exists {
			return fmt.Errorf(
				"shell UI surface %q references unknown route %q",
				id,
				routeID,
			)
		}
		if routePath != pathTemplate {
			return fmt.Errorf(
				"shell UI surface %q path %q differs from route %q path %q",
				id,
				pathTemplate,
				routeID,
				routePath,
			)
		}
		surfaceIDs[id] = struct{}{}
	}
	if err := validateLinkTemplates(
		documents.routes,
		documents.linkTemplates,
	); err != nil {
		return fmt.Errorf("validate shell navigation link templates: %w", err)
	}
	return nil
}

func renderShellNavigationArtifacts(
	appDir string,
	documents *shellNavigationDocuments,
) []shellNavigationArtifact {
	rendered := map[string]string{
		"app_pages.g.dart": renderAppPagesDart(
			documents.pages,
			documents.routes,
		),
		"app_route_paths.g.dart": renderAppRoutePathsDart(
			documents.routes.Routes,
		),
		"app_ui_surfaces.g.dart": renderAppUISurfacesDart(
			documents.surfaces.Surfaces,
		),
		"link_templates.g.dart": renderLinkTemplatesDart(
			documents.linkTemplates,
			documents.routes,
		),
		"page_access_internal_routes.g.dart": renderPageAccessInternalRoutesDart(
			documents.pages,
		),
	}
	artifacts := make([]shellNavigationArtifact, 0, len(rendered))
	for _, name := range shellNavigationOutputNames {
		absolutePath := runtimeNavigationOutputPath(appDir, name)
		relativePath, err := filepath.Rel(appDir, absolutePath)
		if err != nil {
			exitErr(fmt.Errorf("resolve shell navigation output %s: %w", name, err))
		}
		artifacts = append(artifacts, shellNavigationArtifact{
			relativePath: filepath.ToSlash(relativePath),
			content:      []byte(rendered[name]),
		})
	}
	return artifacts
}

func buildShellNavigationManifest(
	artifacts []shellNavigationArtifact,
) (shellNavigationManifest, error) {
	inputs := make([]shellNavigationInput, 0, len(shellNavigationMetadataPaths))
	metadataDigest := sha256.New()
	for _, path := range shellNavigationMetadataPaths {
		if activeMetadataSource == nil {
			return shellNavigationManifest{}, fmt.Errorf(
				"shell navigation ContractGraph Source is not initialized",
			)
		}
		content, err := activeMetadataSource.Content(path)
		if err != nil {
			return shellNavigationManifest{}, fmt.Errorf(
				"read shell navigation source %s: %w",
				path,
				err,
			)
		}
		sum := sha256.Sum256(content)
		digest := hex.EncodeToString(sum[:])
		inputs = append(inputs, shellNavigationInput{
			Path:   path,
			SHA256: digest,
		})
		_, _ = metadataDigest.Write([]byte(path))
		_, _ = metadataDigest.Write([]byte{0})
		_, _ = metadataDigest.Write([]byte(digest))
		_, _ = metadataDigest.Write([]byte{'\n'})
	}
	outputs := make([]shellNavigationOutput, 0, len(artifacts))
	for _, artifact := range artifacts {
		sum := sha256.Sum256(artifact.content)
		outputs = append(outputs, shellNavigationOutput{
			Path:      artifact.relativePath,
			Owner:     shellNavigationOwner,
			Generator: shellNavigationGenerator,
			SHA256:    hex.EncodeToString(sum[:]),
			Bytes:     len(artifact.content),
		})
	}
	sort.Slice(outputs, func(i, j int) bool {
		return outputs[i].Path < outputs[j].Path
	})
	return shellNavigationManifest{
		Generator:      shellNavigationGenerator,
		Responsibility: shellNavigationMode,
		MetadataSHA256: hex.EncodeToString(metadataDigest.Sum(nil)),
		Inputs:         inputs,
		Outputs:        outputs,
	}, nil
}

func checkShellNavigationArtifacts(
	appDir string,
	manifestPath string,
	artifacts []shellNavigationArtifact,
	expectedManifest shellNavigationManifest,
) error {
	expectedPaths := make(map[string]struct{}, len(artifacts))
	for _, artifact := range artifacts {
		expectedPaths[artifact.relativePath] = struct{}{}
		path := filepath.Join(appDir, filepath.FromSlash(artifact.relativePath))
		actual, err := os.ReadFile(path)
		if err != nil {
			return fmt.Errorf(
				"shell navigation generated output missing: %s; run make codegen-app-shell-navigation",
				artifact.relativePath,
			)
		}
		if !reflect.DeepEqual(actual, artifact.content) {
			return fmt.Errorf(
				"shell navigation generated output is stale: %s; run make codegen-app-shell-navigation",
				artifact.relativePath,
			)
		}
	}
	discovered, err := discoverShellNavigationGeneratedFiles(appDir)
	if err != nil {
		return err
	}
	for path := range discovered {
		if _, expected := expectedPaths[path]; !expected {
			return fmt.Errorf(
				"orphan shell navigation generated output: %s; run make codegen-app-shell-navigation",
				path,
			)
		}
	}
	actualManifest, err := readShellNavigationManifest(manifestPath)
	if err != nil {
		return fmt.Errorf(
			"shell navigation generated manifest is missing or invalid: %w; run make codegen-app-shell-navigation",
			err,
		)
	}
	if !reflect.DeepEqual(actualManifest, expectedManifest) {
		return fmt.Errorf(
			"shell navigation generated manifest is stale: %s; run make codegen-app-shell-navigation",
			manifestPath,
		)
	}
	fmt.Printf(
		"PASS: shell navigation metadata outputs are current (outputs=%d, metadata=%s)\n",
		len(expectedManifest.Outputs),
		expectedManifest.MetadataSHA256,
	)
	return nil
}

func writeShellNavigationArtifacts(
	appDir string,
	manifestPath string,
	artifacts []shellNavigationArtifact,
	manifest shellNavigationManifest,
) error {
	expectedPaths := make(map[string]struct{}, len(artifacts))
	for _, artifact := range artifacts {
		expectedPaths[artifact.relativePath] = struct{}{}
		path := filepath.Join(appDir, filepath.FromSlash(artifact.relativePath))
		if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
			return fmt.Errorf("create shell navigation output directory: %w", err)
		}
		if err := os.WriteFile(path, artifact.content, 0o644); err != nil {
			return fmt.Errorf(
				"write shell navigation generated output %s: %w",
				path,
				err,
			)
		}
		fmt.Printf("generated: %s\n", path)
	}
	discovered, err := discoverShellNavigationGeneratedFiles(appDir)
	if err != nil {
		return err
	}
	for relativePath := range discovered {
		if _, expected := expectedPaths[relativePath]; expected {
			continue
		}
		path := filepath.Join(appDir, filepath.FromSlash(relativePath))
		if err := os.Remove(path); err != nil {
			return fmt.Errorf(
				"remove orphan shell navigation generated output %s: %w",
				path,
				err,
			)
		}
		fmt.Printf("retired generated: %s\n", path)
	}
	payload, err := json.MarshalIndent(manifest, "", "  ")
	if err != nil {
		return fmt.Errorf("encode shell navigation generated manifest: %w", err)
	}
	payload = append(payload, '\n')
	if err := os.MkdirAll(filepath.Dir(manifestPath), 0o755); err != nil {
		return fmt.Errorf(
			"create shell navigation manifest directory: %w",
			err,
		)
	}
	if err := os.WriteFile(manifestPath, payload, 0o644); err != nil {
		return fmt.Errorf(
			"write shell navigation generated manifest: %w",
			err,
		)
	}
	fmt.Printf("generated manifest: %s\n", manifestPath)
	return nil
}

func discoverShellNavigationGeneratedFiles(
	appDir string,
) (map[string]struct{}, error) {
	root := filepath.Dir(runtimeNavigationOutputPath(appDir, "placeholder.dart"))
	discovered := map[string]struct{}{}
	if _, err := os.Stat(root); err != nil {
		if os.IsNotExist(err) {
			return discovered, nil
		}
		return nil, fmt.Errorf("inspect shell navigation output root: %w", err)
	}
	err := filepath.WalkDir(root, func(
		path string,
		entry os.DirEntry,
		walkErr error,
	) error {
		if walkErr != nil {
			return walkErr
		}
		if entry.IsDir() || filepath.Ext(path) != ".dart" {
			return nil
		}
		payload, err := os.ReadFile(path)
		if err != nil {
			return err
		}
		header := strings.ToLower(string(payload[:min(len(payload), 300)]))
		if !strings.Contains(header, "generated") ||
			!strings.Contains(header, "do not edit") {
			return nil
		}
		relativePath, err := filepath.Rel(appDir, path)
		if err != nil {
			return err
		}
		discovered[filepath.ToSlash(relativePath)] = struct{}{}
		return nil
	})
	if err != nil {
		return nil, fmt.Errorf(
			"scan shell navigation generated outputs: %w",
			err,
		)
	}
	return discovered, nil
}

func readShellNavigationManifest(
	path string,
) (shellNavigationManifest, error) {
	payload, err := os.ReadFile(path)
	if err != nil {
		return shellNavigationManifest{}, err
	}
	var manifest shellNavigationManifest
	if err := json.Unmarshal(payload, &manifest); err != nil {
		return shellNavigationManifest{}, err
	}
	return manifest, nil
}
