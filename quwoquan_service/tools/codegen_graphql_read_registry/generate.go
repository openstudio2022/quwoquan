package main

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"sort"
	"strings"

	"github.com/vektah/gqlparser/v2"
	"github.com/vektah/gqlparser/v2/ast"
	contractcodegen "quwoquan_service/internal/metadata/codegen"
	contractvalidate "quwoquan_service/internal/metadata/validate"
)

func Generate(options Options) ([]byte, error) {
	if strings.TrimSpace(options.MetadataDir) == "" {
		return nil, errors.New("metadataDir is required")
	}
	source, err := contractcodegen.NewSource(
		options.MetadataDir,
		contractvalidate.ProfileBaseline,
	)
	if err != nil {
		return nil, fmt.Errorf("load ContractGraph Source: %w", err)
	}
	return generateWithSource(options, source)
}

func generateWithSource(options Options, source *contractcodegen.Source) ([]byte, error) {
	if !digestPattern.MatchString(options.CandidateDigest) {
		return nil, errors.New("candidateDigest must be canonical sha256")
	}
	schemaBytes, err := readRegularBytes(options.SchemaPath, "GraphQL schema")
	if err != nil {
		return nil, err
	}
	schema, err := gqlparser.LoadSchema(&ast.Source{
		Name: options.SchemaPath, Input: string(schemaBytes),
	})
	if err != nil {
		return nil, fmt.Errorf("parse GraphQL schema: %w", err)
	}
	if schema.Query == nil {
		return nil, errors.New("GraphQL schema must define Query")
	}
	if schema.Mutation != nil || schema.Subscription != nil {
		return nil, errors.New("GraphQL read schema must not define Mutation or Subscription")
	}
	metadata, err := loadMetadata(options.MetadataPath)
	if err != nil {
		return nil, err
	}
	metadataRoot := filepath.Dir(options.MetadataPath)
	entries := make([]RegistryEntry, 0, len(metadata.Entries))
	seenHashes := map[string]string{}
	seenOperationNames := map[string]string{}
	for _, entryMetadata := range metadata.Entries {
		operationBinding, err := deriveOperationBinding(source, entryMetadata.CanonicalOperationID)
		if err != nil {
			return nil, err
		}
		documentPath := filepath.Join(metadataRoot, filepath.FromSlash(entryMetadata.Document))
		documentBytes, err := readRegularBytes(documentPath, "persisted query document")
		if err != nil {
			return nil, fmt.Errorf("operation %s: %w", entryMetadata.CanonicalOperationID, err)
		}
		document, queryErrors := gqlparser.LoadQuery(schema, string(documentBytes))
		if queryErrors != nil {
			return nil, fmt.Errorf("operation %s: parse persisted query: %w", entryMetadata.CanonicalOperationID, queryErrors)
		}
		if len(document.Operations) != 1 {
			return nil, fmt.Errorf("operation %s: document must contain exactly one operation", entryMetadata.CanonicalOperationID)
		}
		operation := document.Operations[0]
		if operation == nil || !graphQLName.MatchString(operation.Name) {
			return nil, fmt.Errorf("operation %s: persisted document must declare one named operation", entryMetadata.CanonicalOperationID)
		}
		operationBinding.operationName = operation.Name
		ownerBinding, err := loadOwnerPersistedQuery(
			source,
			entryMetadata,
			operationBinding,
			operation.Name,
			documentBytes,
		)
		if err != nil {
			return nil, fmt.Errorf("operation %s: %w", operation.Name, err)
		}
		appClientBundle, err := projectAppClientBundle(
			schema, document, operation, ownerBinding,
		)
		if err != nil {
			return nil, fmt.Errorf("operation %s: %w", operation.Name, err)
		}
		summary, err := analyzeOperation(schema, document, operation)
		if err != nil {
			return nil, fmt.Errorf("operation %s: %w", operation.Name, err)
		}
		if err := validateComputedCost(entryMetadata, summary); err != nil {
			return nil, fmt.Errorf("operation %s: %w", operation.Name, err)
		}
		multipliers := sortedMultipliers(summary.multipliers)
		pageSizeMax := 1
		paginationVariables := make([]string, 0, len(multipliers))
		for _, multiplier := range multipliers {
			paginationVariables = append(paginationVariables, multiplier.VariablePath)
			if multiplier.MaximumValue > pageSizeMax {
				pageSizeMax = multiplier.MaximumValue
			}
		}
		plan := CostPlan{
			BaseComplexity: summary.base, ListMultipliers: multipliers,
			MaxOwnerCalls:    entryMetadata.MaxOwnerCalls,
			MaxBatchKeys:     entryMetadata.MaxBatchKeys,
			MaxResponseBytes: entryMetadata.MaxResponseBytes,
		}
		planBytes, err := json.Marshal(plan)
		if err != nil {
			return nil, fmt.Errorf("operation %s: encode CostPlan: %w", operation.Name, err)
		}
		documentHash := sha256.Sum256(documentBytes)
		hash := hex.EncodeToString(documentHash[:])
		if previous, exists := seenOperationNames[operation.Name]; exists {
			return nil, fmt.Errorf("operations %s and %s have duplicate operationName %s", previous, entryMetadata.CanonicalOperationID, operation.Name)
		}
		seenOperationNames[operation.Name] = entryMetadata.CanonicalOperationID
		if previous, exists := seenHashes[hash]; exists {
			return nil, fmt.Errorf("operations %s and %s have the same document hash", previous, operation.Name)
		}
		seenHashes[hash] = operation.Name
		entries = append(entries, RegistryEntry{
			SHA256Hash: hash, OperationName: operation.Name,
			OperationType: operationBinding.operationType, CanonicalOperationID: entryMetadata.CanonicalOperationID,
			ObjectIDs: append([]string(nil), operationBinding.objectIDs...),
			Authorization: authorizationMetadata{
				Principal:       operationBinding.authorization.Principal,
				Scopes:          append([]string{}, operationBinding.authorization.Scopes...),
				OwnershipPolicy: operationBinding.authorization.OwnershipPolicy,
			},
			CostModelVersion: costModelVersion,
			CostPlanDigest:   digestBytes(planBytes),
			Cost: CostBudget{
				Depth: summary.depth, TopLevelFields: summary.fieldCount,
				Complexity: summary.worst, VariablesMaxBytes: entryMetadata.VariablesMaxBytes,
				PageSizeMax: pageSizeMax, MaxOwnerCalls: entryMetadata.MaxOwnerCalls,
				MaxBatchKeys:     entryMetadata.MaxBatchKeys,
				MaxResponseBytes: entryMetadata.MaxResponseBytes, SLORef: entryMetadata.SLORef,
				DepthExceptionRef:      entryMetadata.DepthExceptionRef,
				TopLevelExceptionRef:   entryMetadata.TopLevelExceptionRef,
				ComplexityExceptionRef: entryMetadata.ComplexityExceptionRef,
			},
			CostPlan: plan, PaginationVariables: paginationVariables,
			ExecutorKey: entryMetadata.ExecutorKey, AppClientBundle: appClientBundle,
		})
	}
	if err := validateRegistryBundles(entries); err != nil {
		return nil, err
	}
	sort.Slice(entries, func(left, right int) bool {
		return entries[left].SHA256Hash < entries[right].SHA256Hash
	})
	registry := RegistryDocument{
		CandidateDigest: options.CandidateDigest,
		SchemaDigest:    digestBytes(schemaBytes),
		Entries:         entries,
	}
	encoded, err := json.MarshalIndent(registry, "", "  ")
	if err != nil {
		return nil, fmt.Errorf("encode persisted query registry: %w", err)
	}
	return append(encoded, '\n'), nil
}

func validateComputedCost(metadata metadataEntry, summary costSummary) error {
	if summary.depth > 5 {
		return fmt.Errorf("depth=%d exceeds absolute maximum 5", summary.depth)
	}
	if summary.depth > 3 && metadata.DepthExceptionRef == "" {
		return fmt.Errorf("depth=%d requires depthExceptionRef", summary.depth)
	}
	if summary.depth <= 3 && metadata.DepthExceptionRef != "" {
		return errors.New("depthExceptionRef is forbidden when depth is within 1..3")
	}
	if summary.fieldCount > 5 {
		return fmt.Errorf("topLevelFields=%d exceeds absolute maximum 5", summary.fieldCount)
	}
	if summary.fieldCount > 3 && metadata.TopLevelExceptionRef == "" {
		return fmt.Errorf("topLevelFields=%d requires topLevelExceptionRef", summary.fieldCount)
	}
	if summary.fieldCount <= 3 && metadata.TopLevelExceptionRef != "" {
		return errors.New("topLevelExceptionRef is forbidden when top-level fields are within 1..3")
	}
	if summary.worst > 1000 {
		return fmt.Errorf("complexity=%d exceeds absolute maximum 1000", summary.worst)
	}
	regularLimit, _ := queryClassComplexityLimit(metadata.QueryClass)
	if summary.worst > regularLimit && metadata.ComplexityExceptionRef == "" {
		return fmt.Errorf(
			"queryClass=%s complexity=%d requires complexityExceptionRef above %d",
			metadata.QueryClass, summary.worst, regularLimit,
		)
	}
	if summary.worst <= regularLimit && metadata.ComplexityExceptionRef != "" {
		return fmt.Errorf(
			"complexityExceptionRef is forbidden within queryClass=%s limit %d",
			metadata.QueryClass, regularLimit,
		)
	}
	calculatedWorst := summary.base
	for _, multiplier := range summary.multipliers {
		calculatedWorst += multiplier.Coefficient *
			(multiplier.MaximumValue - multiplier.DefaultValue)
	}
	if calculatedWorst != summary.worst {
		return fmt.Errorf("CostPlan worstCase=%d differs from AST complexity=%d", calculatedWorst, summary.worst)
	}
	return nil
}

func readRegularBytes(path string, label string) ([]byte, error) {
	file, err := openRegular(path, label)
	if err != nil {
		return nil, err
	}
	defer file.Close()
	encoded, err := io.ReadAll(file)
	if err != nil {
		return nil, fmt.Errorf("read %s: %w", label, err)
	}
	return encoded, nil
}

func digestBytes(encoded []byte) string {
	digest := sha256.Sum256(encoded)
	return "sha256:" + hex.EncodeToString(digest[:])
}

func WriteOrCheck(path string, encoded []byte, check bool) error {
	if check {
		current, err := readRegularBytes(path, "generated registry")
		if err != nil {
			return err
		}
		if !bytes.Equal(current, encoded) {
			return errors.New("generated persisted query registry is stale")
		}
		return nil
	}
	if info, err := os.Lstat(path); err == nil && !info.Mode().IsRegular() {
		return errors.New("generated registry output must be a regular file")
	} else if err != nil && !os.IsNotExist(err) {
		return fmt.Errorf("inspect generated registry output: %w", err)
	}
	parent := filepath.Dir(path)
	if err := os.MkdirAll(parent, 0o755); err != nil {
		return fmt.Errorf("create generated registry directory: %w", err)
	}
	temporary, err := os.CreateTemp(parent, ".graphql-read-registry-*.tmp")
	if err != nil {
		return fmt.Errorf("create generated registry temporary: %w", err)
	}
	temporaryPath := temporary.Name()
	defer os.Remove(temporaryPath)
	if err := temporary.Chmod(0o644); err != nil {
		temporary.Close()
		return err
	}
	if _, err := temporary.Write(encoded); err != nil {
		temporary.Close()
		return fmt.Errorf("write generated registry: %w", err)
	}
	if err := temporary.Sync(); err != nil {
		temporary.Close()
		return fmt.Errorf("sync generated registry: %w", err)
	}
	if err := temporary.Close(); err != nil {
		return fmt.Errorf("close generated registry: %w", err)
	}
	if err := os.Rename(temporaryPath, path); err != nil {
		return fmt.Errorf("publish generated registry: %w", err)
	}
	readback, err := readRegularBytes(path, "generated registry")
	if err != nil {
		return err
	}
	if !bytes.Equal(readback, encoded) {
		return errors.New("generated registry readback differs from rendered bytes")
	}
	return nil
}

func normalizedPath(path string) string {
	return strings.TrimSpace(filepath.Clean(path))
}
