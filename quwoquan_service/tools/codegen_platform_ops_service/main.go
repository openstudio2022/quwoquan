package main

import (
	"flag"
	"fmt"
	"go/format"
	"os"
	"path/filepath"

	contractcodegen "quwoquan_service/internal/metadata/codegen"
	"quwoquan_service/internal/metadata/validate"
)

func main() {
	var metadataDir string
	var outputDir string
	flag.StringVar(&metadataDir, "metadata-dir", "contracts/metadata", "metadata root directory")
	flag.StringVar(&outputDir, "output-dir", "control-plane/platform-ops/generated/platform_ops/config_snapshot", "platform-ops generated object directory")
	flag.Parse()

	source, err := contractcodegen.NewSource(metadataDir, validate.ProfileBaseline)
	if err != nil {
		exitErr(fmt.Errorf("compile ContractGraph: %w", err))
	}
	var errorsFile contractcodegen.ErrorsFile
	const sourcePath = "ops/platform_ops/config_snapshot/errors.yaml"
	if err := source.Decode(sourcePath, &errorsFile); err != nil {
		exitErr(fmt.Errorf("load %s: %w", sourcePath, err))
	}
	rendered := contractcodegen.RenderGoErrorsFile(&errorsFile, contractcodegen.GoErrorsFileOptions{
		Generator:    "tools/codegen_platform_ops_service",
		SourcePath:   sourcePath,
		CommentLines: []string{"PlatformOps ConfigLayer error sentinels and helpers."},
	})
	formatted, err := format.Source([]byte(rendered))
	if err != nil {
		exitErr(fmt.Errorf("gofmt generated errors: %w", err))
	}
	outPath := filepath.Join(outputDir, "errors.go")
	if err := os.MkdirAll(filepath.Dir(outPath), 0o755); err != nil {
		exitErr(err)
	}
	if err := os.WriteFile(outPath, formatted, 0o644); err != nil {
		exitErr(err)
	}
	fmt.Printf("codegen_platform_ops_service: wrote %d errors to %s\n", len(errorsFile.Errors), outPath)
}

func exitErr(err error) {
	fmt.Fprintf(os.Stderr, "codegen_platform_ops_service error: %v\n", err)
	os.Exit(1)
}
