package main

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"
)

const appOnlyEmitter = "app-only-emitter"

type generatedOutput struct {
	Path                string `json:"path"`
	Owner               string `json:"owner"`
	Generator           string `json:"generator"`
	ContractGraphSHA256 string `json:"contractGraphSha256"`
	SHA256              string `json:"sha256"`
	Bytes               int    `json:"bytes"`
}

type appGeneratedManifest struct {
	Generator           string            `json:"generator"`
	ContractGraphSHA256 string            `json:"contractGraphSha256"`
	Outputs             []generatedOutput `json:"outputs"`
}

var (
	generatedManifestAppRoot string
	generatedManifestGraph   string
	generatedManifestOutputs = map[string]generatedOutput{}
)

func beginGeneratedManifest(appDir, graphSHA256 string) {
	root, err := filepath.Abs(appDir)
	if err != nil {
		exitErr(fmt.Errorf("resolve App root for generated manifest: %w", err))
	}
	generatedManifestAppRoot = filepath.Clean(root)
	generatedManifestGraph = graphSHA256
	generatedManifestOutputs = map[string]generatedOutput{}
}

func recordGeneratedFile(path string, content []byte) {
	if generatedManifestAppRoot == "" {
		return
	}
	absolute, err := filepath.Abs(path)
	if err != nil {
		exitErr(fmt.Errorf("resolve generated output %s: %w", path, err))
	}
	relative, err := filepath.Rel(
		generatedManifestAppRoot,
		filepath.Clean(absolute),
	)
	if err != nil ||
		relative == ".." ||
		strings.HasPrefix(relative, ".."+string(filepath.Separator)) {
		exitErr(fmt.Errorf(
			"App-only emitter attempted to write outside App root: %s",
			path,
		))
	}
	sum := sha256.Sum256(content)
	normalized := filepath.ToSlash(relative)
	generatedManifestOutputs[normalized] = generatedOutput{
		Path:                normalized,
		Owner:               "app-only-emitter",
		Generator:           appOnlyEmitter,
		ContractGraphSHA256: generatedManifestGraph,
		SHA256:              hex.EncodeToString(sum[:]),
		Bytes:               len(content),
	}
}

func writeGeneratedManifest(path string) error {
	outputs := make([]generatedOutput, 0, len(generatedManifestOutputs))
	for _, output := range generatedManifestOutputs {
		outputs = append(outputs, output)
	}
	sort.Slice(outputs, func(i, j int) bool {
		return outputs[i].Path < outputs[j].Path
	})
	manifest := appGeneratedManifest{
		Generator:           appOnlyEmitter,
		ContractGraphSHA256: generatedManifestGraph,
		Outputs:             outputs,
	}
	data, err := json.MarshalIndent(manifest, "", "  ")
	if err != nil {
		return fmt.Errorf("encode App generated manifest: %w", err)
	}
	data = append(data, '\n')
	if err := os.MkdirAll(filepath.Dir(path), 0755); err != nil {
		return fmt.Errorf("create App generated manifest directory: %w", err)
	}
	if err := os.WriteFile(path, data, 0644); err != nil {
		return fmt.Errorf("write App generated manifest: %w", err)
	}
	fmt.Printf("generated manifest: %s\n", path)
	return nil
}
