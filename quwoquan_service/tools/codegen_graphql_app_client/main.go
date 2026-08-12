package main

import (
	"bytes"
	"errors"
	"flag"
	"fmt"
	"os"
	"path/filepath"
)

func main() {
	var options Options
	var appDir string
	var outputPath string
	var manifestPath string
	var target string
	var check bool
	flag.StringVar(&target, "target", "content-post-detail", "generated App client target: content-post-detail or search-page")
	flag.StringVar(&options.MetadataDir, "metadata-dir", "contracts/metadata", "compiled ContractGraph metadata source")
	flag.StringVar(
		&options.RegistryPath,
		"registry",
		"services/api-edge/resources/policies/graphql_read/persisted_query_registry.example.json",
		"generated persisted GraphQL registry",
	)
	flag.StringVar(
		&options.MetadataPath,
		"metadata",
		"services/api-edge/resources/policies/graphql_read/query_metadata.json",
		"persisted GraphQL query metadata",
	)
	flag.StringVar(
		&options.SchemaPath,
		"schema",
		"services/api-edge/resources/policies/graphql_read/schema.graphqls",
		"GraphQL read schema source",
	)
	flag.StringVar(
		&options.ContractGraphPath,
		"contract-graph",
		"generated/contract_graph.json",
		"fresh ContractGraph",
	)
	flag.StringVar(
		&options.AppLockPath,
		"app-lock",
		"../quwoquan_app/tool/cloud_codegen/contract_graph.lock.json",
		"accepted App ContractGraph lock",
	)
	flag.StringVar(&appDir, "app-dir", "../quwoquan_app", "App repository root")
	flag.StringVar(
		&outputPath,
		"output",
		appClientOutputPath,
		"generated Dart path below App root",
	)
	flag.StringVar(
		&manifestPath,
		"manifest",
		"tool/graphql_read_codegen/generated_manifest.json",
		"generated manifest path below App root",
	)
	flag.BoolVar(&check, "check", false, "fail unless generated outputs are byte-current")
	flag.Parse()

	var generated []byte
	var manifest []byte
	var err error
	switch target {
	case "content-post-detail":
		generated, manifest, err = Generate(options)
	case "search-page":
		if outputPath == appClientOutputPath {
			outputPath = searchAppClientOutputPath
		}
		if manifestPath == "tool/graphql_read_codegen/generated_manifest.json" {
			manifestPath = searchAppManifestPath
		}
		generated, manifest, err = GenerateSearch(options)
	default:
		err = fmt.Errorf("unsupported generated App client target %q", target)
	}
	if err == nil {
		err = writeOrCheckBelow(appDir, outputPath, generated, check)
	}
	if err == nil {
		err = writeOrCheckBelow(appDir, manifestPath, manifest, check)
	}
	if err != nil {
		fmt.Fprintln(os.Stderr, "codegen_graphql_app_client:", err)
		os.Exit(1)
	}
}

func writeOrCheckBelow(root, relative string, content []byte, check bool) error {
	if filepath.IsAbs(relative) {
		return errors.New("generated output path must be relative to App root")
	}
	cleanRoot, err := filepath.Abs(root)
	if err != nil {
		return fmt.Errorf("resolve App root: %w", err)
	}
	path, err := filepath.Abs(filepath.Join(cleanRoot, relative))
	if err != nil {
		return fmt.Errorf("resolve generated output: %w", err)
	}
	inside, err := filepath.Rel(cleanRoot, path)
	if err != nil || inside == ".." || len(inside) > 3 && inside[:3] == ".."+string(filepath.Separator) {
		return errors.New("generated output escaped App root")
	}
	if check {
		current, err := readRegularFile(path, "generated App output")
		if err != nil {
			return err
		}
		if !bytes.Equal(current, content) {
			return fmt.Errorf("generated App output is stale: %s", relative)
		}
		return nil
	}
	if info, err := os.Lstat(path); err == nil && !info.Mode().IsRegular() {
		return fmt.Errorf("generated App output must be a regular file: %s", relative)
	} else if err != nil && !os.IsNotExist(err) {
		return fmt.Errorf("inspect generated App output: %w", err)
	}
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		return fmt.Errorf("create generated output directory: %w", err)
	}
	temporary, err := os.CreateTemp(filepath.Dir(path), ".graphql-app-client-*.tmp")
	if err != nil {
		return fmt.Errorf("create generated output temporary: %w", err)
	}
	temporaryPath := temporary.Name()
	defer os.Remove(temporaryPath)
	if err := temporary.Chmod(0o644); err != nil {
		temporary.Close()
		return err
	}
	if _, err := temporary.Write(content); err != nil {
		temporary.Close()
		return fmt.Errorf("write generated output: %w", err)
	}
	if err := temporary.Sync(); err != nil {
		temporary.Close()
		return fmt.Errorf("sync generated output: %w", err)
	}
	if err := temporary.Close(); err != nil {
		return fmt.Errorf("close generated output: %w", err)
	}
	if err := os.Rename(temporaryPath, path); err != nil {
		return fmt.Errorf("publish generated output: %w", err)
	}
	readback, err := readRegularFile(path, "generated App output")
	if err != nil {
		return err
	}
	if !bytes.Equal(readback, content) {
		return fmt.Errorf("generated App output readback differs: %s", relative)
	}
	return nil
}
