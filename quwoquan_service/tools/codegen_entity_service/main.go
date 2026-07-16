// Command codegen_entity_service generates entity-service contract artifacts.
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

const homepageErrorsSource = "entity/homepage/errors.yaml"

func main() {
	var metadataDir string
	var outputDir string
	flag.StringVar(&metadataDir, "metadata-dir", "contracts/metadata", "metadata root directory")
	flag.StringVar(&outputDir, "output-dir", "services/entity-service/internal", "entity-service internal output directory")
	flag.Parse()

	source, err := contractcodegen.NewSource(metadataDir, validate.ProfileBaseline)
	if err != nil {
		exitErr(fmt.Errorf("compile ContractGraph: %w", err))
	}
	if err := generateErrors(source, outputDir); err != nil {
		exitErr(fmt.Errorf("generate entity homepage errors: %w", err))
	}
	fmt.Printf("codegen_entity_service: wrote homepage errors under %s\n", outputDir)
}

func generateErrors(source *contractcodegen.Source, outputDir string) error {
	var errorsFile contractcodegen.ErrorsFile
	if err := source.Decode(homepageErrorsSource, &errorsFile); err != nil {
		return fmt.Errorf("load %s: %w", homepageErrorsSource, err)
	}
	rendered := contractcodegen.RenderGoErrorsFile(&errorsFile, contractcodegen.GoErrorsFileOptions{
		Generator:    "tools/codegen_entity_service",
		SourcePath:   homepageErrorsSource,
		CommentLines: []string{"Entity homepage error sentinels and helpers. Transport semantics come from errors.yaml."},
	})
	formatted, err := format.Source([]byte(rendered))
	if err != nil {
		return fmt.Errorf("gofmt generated errors: %w", err)
	}
	outPath := filepath.Join(outputDir, "generated", "errors.go")
	if err := os.MkdirAll(filepath.Dir(outPath), 0o755); err != nil {
		return err
	}
	return os.WriteFile(outPath, formatted, 0o644)
}

func exitErr(err error) {
	fmt.Fprintf(os.Stderr, "codegen_entity_service error: %v\n", err)
	os.Exit(1)
}
