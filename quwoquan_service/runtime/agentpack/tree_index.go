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

// TreeIndex represents specs/feature-tree/tree_index.yaml.
type TreeIndex struct {
	Version   int           `yaml:"version" json:"version"`
	UpdatedAt time.Time     `yaml:"updated_at" json:"updatedAt"`
	Features  []FeatureNode `yaml:"features" json:"features"`
}

type FeatureNode struct {
	ID       string        `yaml:"id" json:"id"`
	Name     string        `yaml:"name" json:"name"`
	Level    string        `yaml:"level" json:"level"`
	Path     string        `yaml:"path" json:"path"`
	Domain   string        `yaml:"domain" json:"domain"`
	Status   string        `yaml:"status" json:"status"`
	Tags     []string      `yaml:"tags" json:"tags"`
	Children []FeatureNode `yaml:"children,omitempty" json:"children,omitempty"`
}

// ScanFeatureTree scans a three-level directory tree:
// L1_capability -> L2_feature -> L3_story, while Task remains inside tasks.md.
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
		name := entry.Name()
		if strings.HasPrefix(name, ".") {
			continue
		}
		node, err := scanL1(filepath.Join(rootDir, name), name)
		if err != nil {
			return nil, err
		}
		index.Features = append(index.Features, *node)
	}

	sort.Slice(index.Features, func(i, j int) bool {
		return index.Features[i].ID < index.Features[j].ID
	})
	return index, nil
}

func scanL1(dir, name string) (*FeatureNode, error) {
	node := &FeatureNode{
		ID:     name,
		Name:   name,
		Level:  "L1_capability",
		Path:   dir,
		Status: deriveNodeStatus(dir),
	}

	entries, err := os.ReadDir(dir)
	if err != nil {
		return nil, fmt.Errorf("read l1 dir %s: %w", dir, err)
	}

	for _, entry := range entries {
		if !entry.IsDir() {
			continue
		}
		childName := entry.Name()
		if strings.HasPrefix(childName, ".") {
			continue
		}
		childDir := filepath.Join(dir, childName)
		child, err := scanL2(childDir, childName)
		if err != nil {
			return nil, err
		}
		node.Children = append(node.Children, *child)
	}

	sort.Slice(node.Children, func(i, j int) bool {
		return node.Children[i].ID < node.Children[j].ID
	})

	return node, nil
}

func scanL2(dir, name string) (*FeatureNode, error) {
	node := &FeatureNode{
		ID:     name,
		Name:   name,
		Level:  "L2_feature",
		Path:   dir,
		Status: deriveNodeStatus(dir),
	}

	entries, err := os.ReadDir(dir)
	if err != nil {
		return nil, fmt.Errorf("read l2 dir %s: %w", dir, err)
	}

	for _, entry := range entries {
		if !entry.IsDir() {
			continue
		}
		childName := entry.Name()
		if strings.HasPrefix(childName, ".") {
			continue
		}
		childDir := filepath.Join(dir, childName)
		child, err := scanL3(childDir, childName)
		if err != nil {
			return nil, err
		}
		node.Children = append(node.Children, *child)
	}

	sort.Slice(node.Children, func(i, j int) bool {
		return node.Children[i].ID < node.Children[j].ID
	})

	return node, nil
}

func scanL3(dir, name string) (*FeatureNode, error) {
	node := &FeatureNode{
		ID:     name,
		Name:   name,
		Level:  "L3_story",
		Path:   dir,
		Status: deriveNodeStatus(dir),
	}
	return node, nil
}

func deriveNodeStatus(dir string) string {
	status := "specified"

	tasksPath := filepath.Join(dir, "tasks.md")
	data, err := os.ReadFile(tasksPath)
	if err != nil {
		return status
	}

	content := string(data)
	total := strings.Count(content, "- [")
	done := strings.Count(content, "- [x]")

	switch {
	case total > 0 && done == total:
		return "completed"
	case done > 0:
		return "in_progress"
	default:
		return status
	}
}

func WriteIndex(index *TreeIndex, path string) error {
	data, err := yaml.Marshal(index)
	if err != nil {
		return fmt.Errorf("marshal tree index: %w", err)
	}
	return os.WriteFile(path, data, 0o644)
}

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

	for i, f := range index.Features {
		if f.ID == pack.Feature.Domain || f.Domain == pack.Feature.Domain {
			index.Features[i].Children = append(index.Features[i].Children, node)
			index.UpdatedAt = time.Now().UTC()
			return
		}
	}

	index.Features = append(index.Features, node)
	index.UpdatedAt = time.Now().UTC()
}
