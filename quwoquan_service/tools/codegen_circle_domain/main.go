// Command codegen_circle_domain regenerates every circle bounded-context object
// into its own model/event package. Object packets must never be folded back
// into the Circle aggregate merely to keep old imports compiling.
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
	flag.StringVar(&outputDir, "output-dir", "services/circle-service/internal", "circle-service internal output directory")
	flag.Parse()

	source, err := contractcodegen.NewSource(metadataDir, validate.ProfileBaseline)
	if err != nil {
		exitErr(fmt.Errorf("compile ContractGraph: %w", err))
	}
	generator := contractcodegen.NewDomainGenerator(
		source,
		filepath.Clean(outputDir),
		contractcodegen.WithTypedEnums(),
		contractcodegen.WithSliceEntityRefs(),
		contractcodegen.WithSkipViewEntities(),
		contractcodegen.WithGoFieldIDSuffix(),
		contractcodegen.WithBusinessObjectEntitiesOnly(),
	)
	objects := []string{
		"Circle",
		"CircleBehaviorFact",
		"CircleFile",
		"CircleGroup",
		"CircleGroupMembership",
		"CircleMembership",
		"CirclePostPlacement",
	}
	for _, object := range objects {
		if err := generator.GenerateDomainModel(object); err != nil {
			exitErr(fmt.Errorf("generate %s model: %w", object, err))
		}
		if err := generator.GenerateDomainEvents(object); err != nil {
			exitErr(fmt.Errorf("generate %s events: %w", object, err))
		}
	}
	if err := generateErrors(source, outputDir); err != nil {
		exitErr(fmt.Errorf("generate Circle errors: %w", err))
	}
	fmt.Printf("codegen_circle_domain: wrote %d object model/event packets and errors under %s\n", len(objects), outputDir)
}

func generateErrors(source *contractcodegen.Source, outputDir string) error {
	const sourcePath = "social/circle/errors.yaml"
	var errorsFile contractcodegen.ErrorsFile
	if err := source.Decode(sourcePath, &errorsFile); err != nil {
		return err
	}
	rendered := contractcodegen.RenderGoErrorsFile(&errorsFile, contractcodegen.GoErrorsFileOptions{
		Generator:    "tools/codegen_circle_domain",
		SourcePath:   sourcePath,
		CommentLines: []string{"Circle error sentinels and helpers. user_message and transport semantics come from errors.yaml."},
	})
	formatted, err := format.Source([]byte(rendered))
	if err != nil {
		return fmt.Errorf("gofmt generated errors: %w", err)
	}
	outPath := filepath.Join(outputDir, "generated", "errors.go")
	if err := os.MkdirAll(filepath.Dir(outPath), 0o755); err != nil {
		return err
	}
	if err := os.WriteFile(outPath, formatted, 0o644); err != nil {
		return err
	}
	return nil
}

func exitErr(err error) {
	fmt.Fprintf(os.Stderr, "codegen_circle_domain error: %v\n", err)
	os.Exit(1)
}
