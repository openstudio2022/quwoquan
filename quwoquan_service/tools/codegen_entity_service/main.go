// Command codegen_entity_service generates object-owned entity-service errors.
package main

import (
	"bytes"
	"flag"
	"fmt"
	"go/format"
	"os"
	"path/filepath"

	contractcodegen "quwoquan_service/internal/metadata/codegen"
	"quwoquan_service/internal/metadata/validate"
)

type entityErrorSource struct {
	Context    string
	Object     string
	SourcePath string
}

var entityErrorSources = []entityErrorSource{
	{
		Context:    "entity_homepage",
		Object:     "homepage",
		SourcePath: "entity/entity_homepage/homepage/errors.yaml",
	},
	{
		Context:    "entity_homepage",
		Object:     "homepage_claim_request",
		SourcePath: "entity/entity_homepage/homepage_claim_request/errors.yaml",
	},
	{
		Context:    "entity_homepage",
		Object:     "homepage_review",
		SourcePath: "entity/entity_homepage/homepage_review/errors.yaml",
	},
	{
		Context:    "entity_homepage",
		Object:     "homepage_status_report",
		SourcePath: "entity/entity_homepage/homepage_status_report/errors.yaml",
	},
}

func main() {
	var metadataDir string
	var outputDir string
	var check bool
	flag.StringVar(&metadataDir, "metadata-dir", "contracts/metadata", "metadata root directory")
	flag.StringVar(&outputDir, "output-dir", "services/entity-service/generated", "entity-service generated root directory")
	flag.BoolVar(&check, "check", false, "fail when generated output is stale")
	flag.Parse()

	source, err := contractcodegen.NewSource(metadataDir, validate.ProfileBaseline)
	if err != nil {
		exitErr(fmt.Errorf("compile ContractGraph: %w", err))
	}
	if err := generateErrors(source, outputDir, check); err != nil {
		exitErr(fmt.Errorf("generate entity errors: %w", err))
	}
	verb := "wrote"
	if check {
		verb = "verified"
	}
	fmt.Printf("codegen_entity_service: %s object errors under %s\n", verb, outputDir)
}

func generateErrors(source *contractcodegen.Source, outputDir string, check bool) error {
	for _, item := range entityErrorSources {
		var errorsFile contractcodegen.ErrorsFile
		if err := source.Decode(item.SourcePath, &errorsFile); err != nil {
			return fmt.Errorf("load %s: %w", item.SourcePath, err)
		}
		rendered := contractcodegen.RenderGoErrorsFile(&errorsFile, contractcodegen.GoErrorsFileOptions{
			Generator:    "tools/codegen_entity_service",
			SourcePath:   item.SourcePath,
			CommentLines: []string{"Object-owned error sentinels and helpers. Transport semantics come from errors.yaml."},
		})
		formatted, err := format.Source([]byte(rendered))
		if err != nil {
			return fmt.Errorf("gofmt %s: %w", item.SourcePath, err)
		}
		outPath := filepath.Join(outputDir, item.Context, item.Object, "errors.go")
		if check {
			current, readErr := os.ReadFile(outPath)
			if readErr != nil {
				return fmt.Errorf("read generated output %s: %w", outPath, readErr)
			}
			if !bytes.Equal(current, formatted) {
				return fmt.Errorf("generated output is stale: %s", outPath)
			}
			continue
		}
		if err := os.MkdirAll(filepath.Dir(outPath), 0o755); err != nil {
			return err
		}
		if err := os.WriteFile(outPath, formatted, 0o644); err != nil {
			return err
		}
	}
	return nil
}

func exitErr(err error) {
	fmt.Fprintf(os.Stderr, "codegen_entity_service error: %v\n", err)
	os.Exit(1)
}
