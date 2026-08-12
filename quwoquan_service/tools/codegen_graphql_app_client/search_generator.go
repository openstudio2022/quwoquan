package main

import (
	"encoding/json"
	"errors"
	"fmt"
	"strings"

	contractcodegen "quwoquan_service/internal/metadata/codegen"
	contractvalidate "quwoquan_service/internal/metadata/validate"
)

func GenerateSearch(options Options) ([]byte, []byte, error) {
	if strings.TrimSpace(options.MetadataDir) == "" {
		return nil, nil, errors.New("metadataDir is required")
	}
	source, err := contractcodegen.NewSource(options.MetadataDir, contractvalidate.ProfileBaseline)
	if err != nil {
		return nil, nil, fmt.Errorf("load ContractGraph Source: %w", err)
	}
	return generateSearchWithSource(options, source)
}

func generateSearchWithSource(options Options, source *contractcodegen.Source) ([]byte, []byte, error) {
	input, err := loadSearchGenerationInput(options, source)
	if err != nil {
		return nil, nil, fmt.Errorf("GATE_BLOCK: SearchPage App GraphQL client input: %w", err)
	}
	generated := renderSearchDart(input)
	manifest := generatedManifest{
		Generator: searchAppClientGenerator, RegistrySHA256: input.registryDigest,
		ContractGraphSHA256: input.graphDigest, AppLockSHA256: input.appLockDigest,
		Outputs: []generatedOutput{{
			Path: searchAppClientOutputPath, SHA256: sha256Hex(generated), Bytes: len(generated),
		}},
	}
	manifestBytes, err := json.MarshalIndent(manifest, "", "  ")
	if err != nil {
		return nil, nil, fmt.Errorf("encode SearchPage generated manifest: %w", err)
	}
	return generated, append(manifestBytes, '\n'), nil
}
