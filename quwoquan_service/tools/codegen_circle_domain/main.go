// Command codegen_circle_domain regenerates every circle bounded-context object
// into its service-root generated/<context>/<object>/contract package.
package main

import (
	"flag"
	"fmt"
	"go/format"
	"os"
	"path/filepath"
	"sort"
	"strings"

	contractcodegen "quwoquan_service/internal/metadata/codegen"
	"quwoquan_service/internal/metadata/validate"
)

func main() {
	var metadataDir string
	var outputDir string
	var checkErrors bool
	flag.StringVar(&metadataDir, "metadata-dir", "contracts/metadata", "metadata root directory")
	flag.StringVar(&outputDir, "output-dir", "services/circle-service/generated/circle_management", "circle-service generated context directory")
	flag.BoolVar(&checkErrors, "check-errors", false, "fail when object-owned Circle error outputs are stale")
	flag.Parse()

	source, err := contractcodegen.NewSource(metadataDir, validate.ProfileBaseline)
	if err != nil {
		exitErr(fmt.Errorf("compile ContractGraph: %w", err))
	}
	if checkErrors {
		generatedErrorObjects, err := generateErrors(source, outputDir, true)
		if err != nil {
			exitErr(fmt.Errorf("verify Circle errors: %w", err))
		}
		fmt.Printf("codegen_circle_domain: verified %d object-owned error packets under %s\n", generatedErrorObjects, outputDir)
		return
	}
	objects := []string{
		"Circle",
		"CircleBehaviorFact",
		"CircleFile",
		"CircleGroup",
		"CircleGroupMembership",
		"CircleMembership",
		"CirclePostPlacement",
		"Gathering",
	}
	for _, object := range objects {
		generator := contractcodegen.NewDomainGenerator(
			source,
			filepath.Join(filepath.Clean(outputDir), contractcodegen.CamelToSnake(object)),
			contractcodegen.WithTypedEnums(),
			contractcodegen.WithSliceEntityRefs(),
			contractcodegen.WithSkipViewEntities(),
			contractcodegen.WithGoFieldIDSuffix(),
			contractcodegen.WithBusinessObjectEntitiesOnly(),
			contractcodegen.WithObjectFirstRoot(),
		)
		if err := generator.GenerateDomainModel(object); err != nil {
			exitErr(fmt.Errorf("generate %s model: %w", object, err))
		}
		if err := generator.GenerateDomainEvents(object); err != nil {
			exitErr(fmt.Errorf("generate %s events: %w", object, err))
		}
	}
	generatedErrorObjects, err := generateErrors(source, outputDir, false)
	if err != nil {
		exitErr(fmt.Errorf("generate Circle errors: %w", err))
	}
	fmt.Printf(
		"codegen_circle_domain: wrote %d object model/event packets and %d object-owned error packets under %s\n",
		len(objects),
		generatedErrorObjects,
		outputDir,
	)
}

func generateErrors(source *contractcodegen.Source, outputDir string, check bool) (int, error) {
	errorPaths, err := circleObjectErrorPaths(
		source.Paths("circle/circle_management/", "/errors.yaml"),
	)
	if err != nil {
		return 0, err
	}
	for _, sourcePath := range errorPaths {
		parts := strings.Split(sourcePath, "/")
		var errorsFile contractcodegen.ErrorsFile
		if err := source.Decode(sourcePath, &errorsFile); err != nil {
			return 0, fmt.Errorf("load %s: %w", sourcePath, err)
		}
		rendered := contractcodegen.RenderGoErrorsFile(&errorsFile, contractcodegen.GoErrorsFileOptions{
			Generator:    "tools/codegen_circle_domain",
			SourcePath:   sourcePath,
			CommentLines: []string{"Object-owned Circle errors. Transport semantics come from errors.yaml."},
		})
		formatted, err := format.Source([]byte(rendered))
		if err != nil {
			return 0, fmt.Errorf("gofmt generated errors from %s: %w", sourcePath, err)
		}
		outPath := filepath.Join(outputDir, parts[2], "errors.go")
		if check {
			current, err := os.ReadFile(outPath)
			if err != nil {
				return 0, fmt.Errorf("read generated errors %s: %w", outPath, err)
			}
			if string(current) != string(formatted) {
				return 0, fmt.Errorf("generated errors are stale: %s", outPath)
			}
			continue
		}
		if err := os.MkdirAll(filepath.Dir(outPath), 0o755); err != nil {
			return 0, err
		}
		if err := os.WriteFile(outPath, formatted, 0o644); err != nil {
			return 0, err
		}
	}
	return len(errorPaths), nil
}

func circleObjectErrorPaths(paths []string) ([]string, error) {
	if len(paths) == 0 {
		return nil, fmt.Errorf("Circle metadata has no object-owned errors.yaml")
	}
	result := append([]string(nil), paths...)
	sort.Strings(result)
	for _, sourcePath := range result {
		parts := strings.Split(sourcePath, "/")
		if len(parts) != 4 ||
			parts[0] != "circle" ||
			parts[1] != "circle_management" ||
			strings.TrimSpace(parts[2]) == "" ||
			parts[3] != "errors.yaml" {
			return nil, fmt.Errorf(
				"Circle errors must be owned by exactly one circle_management object: %q",
				sourcePath,
			)
		}
	}
	return result, nil
}

func exitErr(err error) {
	fmt.Fprintf(os.Stderr, "codegen_circle_domain error: %v\n", err)
	os.Exit(1)
}
