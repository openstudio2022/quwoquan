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
	flag.StringVar(&outputDir, "output-dir", "services/user-service/internal", "user-service internal output directory")
	flag.Parse()

	source, err := contractcodegen.NewSource(metadataDir, validate.ProfileBaseline)
	if err != nil {
		exitErr(fmt.Errorf("compile ContractGraph: %w", err))
	}
	merged := contractcodegen.ErrorsFile{Domain: "user"}
	paths := source.Paths("user", "/errors.yaml")
	if len(paths) == 0 {
		exitErr(fmt.Errorf("no user errors metadata found"))
	}
	for _, path := range paths {
		var file contractcodegen.ErrorsFile
		if err := source.Decode(path, &file); err != nil {
			exitErr(fmt.Errorf("load %s: %w", path, err))
		}
		merged.Errors = append(merged.Errors, file.Errors...)
	}
	rendered := contractcodegen.RenderGoErrorsFile(&merged, contractcodegen.GoErrorsFileOptions{
		Generator:    "tools/codegen_user_service",
		SourcePath:   "user/**/errors.yaml",
		CommentLines: []string{"User domain error sentinels and helpers. user_message from errors.yaml user_message.zh."},
	})
	formatted, err := format.Source([]byte(rendered))
	if err != nil {
		exitErr(fmt.Errorf("gofmt generated errors: %w", err))
	}
	outPath := filepath.Join(outputDir, "generated", "errors.go")
	if err := os.MkdirAll(filepath.Dir(outPath), 0o755); err != nil {
		exitErr(err)
	}
	if err := os.WriteFile(outPath, formatted, 0o644); err != nil {
		exitErr(err)
	}
	fmt.Printf("codegen_user_service: wrote %d errors to %s\n", len(merged.Errors), outPath)
}

func exitErr(err error) {
	fmt.Fprintf(os.Stderr, "codegen_user_service error: %v\n", err)
	os.Exit(1)
}
