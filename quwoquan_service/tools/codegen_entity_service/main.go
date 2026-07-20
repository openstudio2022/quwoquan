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

// entityErrorSources 按对象目录聚合 entity 域全部错误码；
// 通用命令错误定义在 homepage/errors.yaml，对象特有错误各归其目录。
var entityErrorSources = []string{
	"entity/homepage/errors.yaml",
	"entity/homepage_claim_request/errors.yaml",
	"entity/homepage_review/errors.yaml",
	"entity/homepage_status_report/errors.yaml",
}

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
		exitErr(fmt.Errorf("generate entity errors: %w", err))
	}
	fmt.Printf("codegen_entity_service: wrote entity errors under %s\n", outputDir)
}

func generateErrors(source *contractcodegen.Source, outputDir string) error {
	merged := contractcodegen.ErrorsFile{}
	seen := map[string]string{}
	for _, sourcePath := range entityErrorSources {
		var errorsFile contractcodegen.ErrorsFile
		if err := source.Decode(sourcePath, &errorsFile); err != nil {
			return fmt.Errorf("load %s: %w", sourcePath, err)
		}
		for _, definition := range errorsFile.Errors {
			if previous, duplicated := seen[definition.Code]; duplicated {
				return fmt.Errorf(
					"error code %s duplicated in %s and %s",
					definition.Code,
					previous,
					sourcePath,
				)
			}
			seen[definition.Code] = sourcePath
			merged.Errors = append(merged.Errors, definition)
		}
	}
	rendered := contractcodegen.RenderGoErrorsFile(&merged, contractcodegen.GoErrorsFileOptions{
		Generator:    "tools/codegen_entity_service",
		SourcePath:   "entity/*/errors.yaml",
		CommentLines: []string{"Entity domain error sentinels and helpers. Transport semantics come from errors.yaml."},
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
