package codegen

import (
	"fmt"
	"path/filepath"
	"sort"
	"strings"

	"quwoquan_service/internal/metadata/compiler"
	"quwoquan_service/internal/metadata/graph"
	"quwoquan_service/internal/metadata/validate"
)

// Source 是 generator 唯一允许使用的 metadata 读取入口。
type Source struct {
	root  string
	graph *graph.ContractGraph
}

func NewSource(metadataDir string, profile validate.Profile) (*Source, error) {
	contractGraph, err := compiler.RequireValid(metadataDir, profile)
	if err != nil {
		return nil, err
	}
	return NewSourceFromGraph(metadataDir, contractGraph), nil
}

func NewSourceFromGraph(
	metadataDir string,
	contractGraph *graph.ContractGraph,
) *Source {
	return &Source{
		root:  filepath.Clean(metadataDir),
		graph: contractGraph,
	}
}

func (s *Source) Graph() *graph.ContractGraph {
	return s.graph
}

func (s *Source) Decode(relativePath string, target any) error {
	return s.graph.DecodeDocumentYAML(normalizeRelativePath(relativePath), target)
}

func (s *Source) Content(relativePath string) ([]byte, error) {
	return s.graph.DocumentContent(normalizeRelativePath(relativePath))
}

func (s *Source) Has(relativePath string) bool {
	return s.graph.HasDocument(normalizeRelativePath(relativePath))
}

func (s *Source) Paths(prefix, suffix string) []string {
	prefix = normalizePrefix(prefix)
	suffix = filepath.ToSlash(suffix)
	var paths []string
	for _, document := range s.graph.Documents {
		if strings.HasPrefix(document.Path, prefix) &&
			strings.HasSuffix(document.Path, suffix) {
			paths = append(paths, document.Path)
		}
	}
	sort.Strings(paths)
	return paths
}

func (s *Source) RelativePath(path string) (string, error) {
	if !filepath.IsAbs(path) && !strings.HasPrefix(filepath.Clean(path), s.root) {
		return normalizeRelativePath(path), nil
	}
	relative, err := filepath.Rel(s.root, filepath.Clean(path))
	if err != nil {
		return "", err
	}
	if relative == ".." ||
		strings.HasPrefix(relative, ".."+string(filepath.Separator)) ||
		filepath.IsAbs(relative) {
		return "", fmt.Errorf("metadata path %s is outside %s", path, s.root)
	}
	return normalizeRelativePath(relative), nil
}

func normalizeRelativePath(path string) string {
	return filepath.ToSlash(filepath.Clean(path))
}

func normalizePrefix(prefix string) string {
	if strings.TrimSpace(prefix) == "" {
		return ""
	}
	return normalizeRelativePath(prefix)
}
