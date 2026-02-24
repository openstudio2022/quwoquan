package agentpack

import (
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"time"

	"gopkg.in/yaml.v3"
)

// TreeIndex represents the feature tree index (tree_index.yaml).
type TreeIndex struct {
	Version   int           `yaml:"version"   json:"version"`
	UpdatedAt time.Time     `yaml:"updated_at" json:"updatedAt"`
	Features  []FeatureNode `yaml:"features"  json:"features"`
}

type FeatureNode struct {
	ID       string        `yaml:"id"       json:"id"`
	Name     string        `yaml:"name"     json:"name"`
	Level    string        `yaml:"level"    json:"level"`
	Path     string        `yaml:"path"     json:"path"`
	Domain   string        `yaml:"domain"   json:"domain"`
	Status   string        `yaml:"status"   json:"status"`
	Tags     []string      `yaml:"tags"     json:"tags"`
	Children []FeatureNode `yaml:"children,omitempty" json:"children,omitempty"`
}

// ScanFeatureTree walks the feature-tree directory and builds an index.
func ScanFeatureTree(rootDir string) (*TreeIndex, error) {
	index := &TreeIndex{
		Version:   1,
		UpdatedAt: time.Now().UTC(),
	}

	entries, err := os.ReadDir(rootDir)
	if err != nil {
		return nil, fmt.Errorf("read feature tree root: %w", err)
	}

	for _, entry := range entries {
		if !entry.IsDir() {
			continue
		}
		node, err := scanFeatureDir(filepath.Join(rootDir, entry.Name()), entry.Name(), "L1_domain")
		if err != nil {
			continue
		}
		index.Features = append(index.Features, *node)
	}

	sort.Slice(index.Features, func(i, j int) bool {
		return index.Features[i].ID < index.Features[j].ID
	})

	return index, nil
}

func scanFeatureDir(dir, name, level string) (*FeatureNode, error) {
	node := &FeatureNode{
		ID:    name,
		Name:  name,
		Level: level,
		Path:  dir,
	}

	// Check for spec.md to extract status
	specPath := filepath.Join(dir, "spec.md")
	if _, err := os.Stat(specPath); err == nil {
		node.Status = "specified"
	}

	tasksPath := filepath.Join(dir, "tasks.md")
	if data, err := os.ReadFile(tasksPath); err == nil {
		content := string(data)
		total := strings.Count(content, "- [")
		done := strings.Count(content, "- [x]")
		if total > 0 && done == total {
			node.Status = "completed"
		} else if done > 0 {
			node.Status = "in_progress"
		} else if node.Status == "" {
			node.Status = "planned"
		}
	}

	// Scan children
	entries, err := os.ReadDir(dir)
	if err != nil {
		return node, nil
	}

	childLevel := nextLevel(level)
	for _, entry := range entries {
		if !entry.IsDir() {
			continue
		}
		child, err := scanFeatureDir(filepath.Join(dir, entry.Name()), entry.Name(), childLevel)
		if err != nil {
			continue
		}
		node.Children = append(node.Children, *child)
	}

	sort.Slice(node.Children, func(i, j int) bool {
		return node.Children[i].ID < node.Children[j].ID
	})

	return node, nil
}

func nextLevel(level string) string {
	switch level {
	case "L1_domain":
		return "L2_feature"
	case "L2_feature":
		return "L3_component"
	case "L3_component":
		return "L4_detail"
	default:
		return "L5_leaf"
	}
}

// WriteIndex serializes the tree index to a YAML file.
func WriteIndex(index *TreeIndex, path string) error {
	data, err := yaml.Marshal(index)
	if err != nil {
		return fmt.Errorf("marshal tree index: %w", err)
	}
	return os.WriteFile(path, data, 0644)
}

// ReadIndex loads a tree index from a YAML file.
func ReadIndex(path string) (*TreeIndex, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var index TreeIndex
	if err := yaml.Unmarshal(data, &index); err != nil {
		return nil, err
	}
	return &index, nil
}

// SearchFeatures performs keyword search across the feature tree.
func SearchFeatures(index *TreeIndex, query string) []FeatureNode {
	query = strings.ToLower(query)
	var results []FeatureNode
	for _, f := range index.Features {
		searchNode(f, query, &results)
	}
	return results
}

func searchNode(node FeatureNode, query string, results *[]FeatureNode) {
	if matchesQuery(node, query) {
		*results = append(*results, node)
	}
	for _, child := range node.Children {
		searchNode(child, query, results)
	}
}

func matchesQuery(node FeatureNode, query string) bool {
	if strings.Contains(strings.ToLower(node.ID), query) {
		return true
	}
	if strings.Contains(strings.ToLower(node.Name), query) {
		return true
	}
	for _, tag := range node.Tags {
		if strings.Contains(strings.ToLower(tag), query) {
			return true
		}
	}
	return false
}

// IngestTaskPack ingests a completed task pack into the feature tree.
func IngestTaskPack(index *TreeIndex, pack TaskPack) {
	node := FeatureNode{
		ID:     pack.Feature.ID,
		Name:   pack.Feature.Name,
		Level:  pack.Feature.Level,
		Path:   pack.Feature.Path,
		Domain: pack.Feature.Domain,
		Tags:   pack.Feature.Tags,
		Status: "completed",
	}

	// Find or create parent
	found := false
	for i, f := range index.Features {
		if f.Domain == pack.Feature.Domain || f.ID == pack.Feature.Domain {
			index.Features[i].Children = append(index.Features[i].Children, node)
			found = true
			break
		}
	}

	if !found {
		index.Features = append(index.Features, node)
	}

	index.UpdatedAt = time.Now().UTC()
}
