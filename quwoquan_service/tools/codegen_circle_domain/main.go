// Command codegen_circle_domain regenerates circle-service domain models from
// contracts/metadata/social/circle (typed enums + slice-of-entity refs). It only
// overwrites the model file; repository/ event stubs stay hand-curated.
package main

import (
	"flag"
	"fmt"
	"os"
	"path/filepath"

	"quwoquan_service/runtime/codegen"
	"quwoquan_service/runtime/registry"
)

func main() {
	var metadataDir string
	var outputDir string
	flag.StringVar(&metadataDir, "metadata-dir", "contracts/metadata", "metadata root directory")
	flag.StringVar(&outputDir, "output-dir", "services/circle-service/internal", "circle-service internal output directory")
	flag.Parse()

	reg, err := registry.LoadFromDirectory(metadataDir)
	if err != nil {
		exitErr(fmt.Errorf("load registry: %w", err))
	}

	g := codegen.NewGenerator(
		reg,
		filepath.Clean(outputDir),
		codegen.WithTypedEnums(),
		codegen.WithSliceEntityRefs(),
		codegen.WithSkipViewEntities(),
		codegen.WithGoFieldIDSuffix(),
	)
	if err := g.GenerateDomainModelOnly("Circle"); err != nil {
		exitErr(fmt.Errorf("generate Circle model: %w", err))
	}
	fmt.Printf("codegen_circle_domain: wrote domain model for aggregate Circle under %s\n", outputDir)
}

func exitErr(err error) {
	fmt.Fprintf(os.Stderr, "codegen_circle_domain error: %v\n", err)
	os.Exit(1)
}
