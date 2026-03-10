package main

import (
	"fmt"
	"os"
	"path/filepath"

	"quwoquan_service/runtime/agentpack"
)

func main() {
	if len(os.Args) < 3 {
		fmt.Fprintf(os.Stderr, "usage: gen_tree_index <feature-tree-dir> <output-yaml>\n")
		os.Exit(1)
	}

	rootDir := os.Args[1]
	outPath := os.Args[2]

	index, err := agentpack.ScanFeatureTree(rootDir)
	if err != nil {
		fmt.Fprintf(os.Stderr, "scan: %v\n", err)
		os.Exit(1)
	}

	rewritePathsRelativeToOutput(index.Features, filepath.Dir(outPath))

	if err := agentpack.WriteIndex(index, outPath); err != nil {
		fmt.Fprintf(os.Stderr, "write: %v\n", err)
		os.Exit(1)
	}

	total := countFeatures(index.Features)
	fmt.Printf("tree_index.yaml generated: %d features written to %s\n", total, outPath)
}

func countFeatures(nodes []agentpack.FeatureNode) int {
	count := len(nodes)
	for _, n := range nodes {
		count += countFeatures(n.Children)
	}
	return count
}

func rewritePathsRelativeToOutput(nodes []agentpack.FeatureNode, outputDir string) {
	for i := range nodes {
		if rel, err := filepath.Rel(outputDir, nodes[i].Path); err == nil {
			nodes[i].Path = rel
		}
		rewritePathsRelativeToOutput(nodes[i].Children, outputDir)
	}
}
