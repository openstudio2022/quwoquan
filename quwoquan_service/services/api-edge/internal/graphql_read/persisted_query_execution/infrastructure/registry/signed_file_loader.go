package registry

import (
	"context"
	"errors"
	"fmt"
	"os"
	"strings"

	"quwoquan_service/services/api-edge/internal/graphql_read/persisted_query_execution/domain"
)

type SignedFileLoader struct {
	verifier domain.SignatureVerifier
}

func NewSignedFileLoader(verifier domain.SignatureVerifier) (*SignedFileLoader, error) {
	if verifier == nil {
		return nil, errors.New("persisted query registry signature verifier is required")
	}
	return &SignedFileLoader{verifier: verifier}, nil
}

func (loader *SignedFileLoader) Load(
	ctx context.Context,
	path string,
	expectedCandidateDigest string,
	expectedSchemaDigest string,
) (*domain.Registry, error) {
	path = strings.TrimSpace(path)
	if path == "" {
		return nil, errors.New("persisted query registry path is required")
	}
	file, err := os.Open(path)
	if err != nil {
		return nil, fmt.Errorf("open persisted query registry: %w", err)
	}
	defer file.Close()
	registry, err := domain.LoadSignedRegistry(
		ctx, file, expectedCandidateDigest, expectedSchemaDigest, loader.verifier,
	)
	if err != nil {
		return nil, fmt.Errorf("load persisted query registry %q: %w", path, err)
	}
	return registry, nil
}
