package main

import (
	"errors"
	"fmt"
	"path/filepath"
	"sort"
	"strings"

	"github.com/vektah/gqlparser/v2"
	"github.com/vektah/gqlparser/v2/ast"
	contractcodegen "quwoquan_service/internal/metadata/codegen"
)

func loadBundleGenerationInput(options Options, source *contractcodegen.Source) (bundleGenerationInput, error) {
	registryBytes, err := readRegularFile(options.RegistryPath, "persisted query registry")
	if err != nil {
		return bundleGenerationInput{}, err
	}
	metadataBytes, err := readRegularFile(options.MetadataPath, "query metadata")
	if err != nil {
		return bundleGenerationInput{}, err
	}
	schemaPath := options.SchemaPath
	if strings.TrimSpace(schemaPath) == "" {
		schemaPath = filepath.Join(filepath.Dir(options.MetadataPath), "schema.graphqls")
	}
	schemaBytes, err := readRegularFile(schemaPath, "GraphQL read schema")
	if err != nil {
		return bundleGenerationInput{}, err
	}
	graphBytes, err := readRegularFile(options.ContractGraphPath, "ContractGraph")
	if err != nil {
		return bundleGenerationInput{}, err
	}
	lockBytes, err := readRegularFile(options.AppLockPath, "App ContractGraph lock")
	if err != nil {
		return bundleGenerationInput{}, err
	}

	var registry registryDocument
	if err := decodeExactJSON(registryBytes, &registry); err != nil {
		return bundleGenerationInput{}, fmt.Errorf("decode persisted query registry: %w", err)
	}
	if !canonicalDigestPattern.MatchString(registry.CandidateDigest) || !canonicalDigestPattern.MatchString(registry.SchemaDigest) {
		return bundleGenerationInput{}, errors.New("persisted query registry digests are not canonical sha256")
	}
	schemaDigest := "sha256:" + sha256Hex(schemaBytes)
	if registry.SchemaDigest != schemaDigest {
		return bundleGenerationInput{}, errors.New("GraphQL schema digest differs from signed registry")
	}
	schema, schemaError := gqlparser.LoadSchema(&ast.Source{Name: schemaPath, Input: string(schemaBytes)})
	if schemaError != nil {
		return bundleGenerationInput{}, fmt.Errorf("load GraphQL read schema: %w", schemaError)
	}

	registryByOperation := map[string]registryEntry{}
	for _, entry := range registry.Entries {
		if entry.AppClientBundle == nil || entry.AppClientBundle.BundleID != detailBundleID {
			continue
		}
		if err := validateDetailRegistryEntry(entry); err != nil {
			return bundleGenerationInput{}, fmt.Errorf("operation %s: %w", entry.OperationName, err)
		}
		if _, exists := registryByOperation[entry.OperationName]; exists {
			return bundleGenerationInput{}, fmt.Errorf("duplicate signed registry operation %s", entry.OperationName)
		}
		registryByOperation[entry.OperationName] = entry
	}
	if len(registryByOperation) == 0 {
		return bundleGenerationInput{}, errors.New("signed registry has no ContentPostDetail App bundle entries")
	}

	var metadata queryMetadataDocument
	if err := decodeExactJSON(metadataBytes, &metadata); err != nil {
		return bundleGenerationInput{}, fmt.Errorf("decode query metadata: %w", err)
	}
	if metadata.Schema != "graphql-read-query-metadata" {
		return bundleGenerationInput{}, errors.New("query metadata schema identity drifted")
	}
	queries := make([]bundleQueryInput, 0, len(registryByOperation))
	slices := make([]bundleSliceInput, 0, len(registryByOperation))
	seenOperations := map[string]bool{}
	for _, metadataEntry := range metadata.Entries {
		if !registryHasCanonicalOperation(registryByOperation, metadataEntry.CanonicalOperationID) {
			continue
		}
		documentPath, err := metadataDocumentPath(options.MetadataPath, metadataEntry.Document)
		if err != nil {
			return bundleGenerationInput{}, err
		}
		documentBytes, err := readRegularFile(documentPath, "persisted GraphQL document")
		if err != nil {
			return bundleGenerationInput{}, err
		}
		document, queryError := gqlparser.LoadQuery(schema, string(documentBytes))
		if queryError != nil {
			return bundleGenerationInput{}, fmt.Errorf("load persisted GraphQL document %s: %w", metadataEntry.Document, queryError)
		}
		if len(document.Operations) != 1 || strings.TrimSpace(document.Operations[0].Name) == "" {
			return bundleGenerationInput{}, fmt.Errorf("persisted document %s must contain exactly one named query", metadataEntry.Document)
		}
		operation := document.Operations[0]
		entry, exists := registryByOperation[operation.Name]
		if !exists {
			return bundleGenerationInput{}, fmt.Errorf("query metadata operation %s is absent from signed registry", operation.Name)
		}
		if seenOperations[operation.Name] {
			return bundleGenerationInput{}, fmt.Errorf("query metadata operation %s is duplicated", operation.Name)
		}
		seenOperations[operation.Name] = true
		if sha256Hex(documentBytes) != entry.SHA256Hash {
			return bundleGenerationInput{}, fmt.Errorf("operation %s document hash differs from signed registry", operation.Name)
		}
		if _, err := exactMetadataEntry(queryMetadataDocument{Schema: metadata.Schema, Entries: []queryMetadataEntry{metadataEntry}}, entry); err != nil {
			return bundleGenerationInput{}, fmt.Errorf("operation %s: %w", operation.Name, err)
		}
		if err := validateDetailVariables(operation, entry); err != nil {
			return bundleGenerationInput{}, fmt.Errorf("operation %s: %w", operation.Name, err)
		}
		responseKey, rootTypeName, selectedFields, err := bundleRootSelection(document, operation)
		if err != nil {
			return bundleGenerationInput{}, fmt.Errorf("operation %s: %w", operation.Name, err)
		}
		queries = append(queries, bundleQueryInput{
			entry: entry, metadata: metadataEntry, responseKey: responseKey,
			rootTypeName: rootTypeName, selectedFields: selectedFields,
		})
		slices = append(slices, bundleSliceInput{
			OperationName: operation.Name, Binding: *entry.AppClientBundle,
			SelectedFields: selectedFields,
		})
	}
	if len(seenOperations) != len(registryByOperation) {
		missing := make([]string, 0)
		for operationName := range registryByOperation {
			if !seenOperations[operationName] {
				missing = append(missing, operationName)
			}
		}
		sort.Strings(missing)
		return bundleGenerationInput{}, fmt.Errorf("signed registry entries lack App generator metadata: %s", strings.Join(missing, ", "))
	}

	var graph contractGraphDocument
	if err := decodeExactJSON(graphBytes, &graph); err != nil {
		return bundleGenerationInput{}, fmt.Errorf("decode ContractGraph: %w", err)
	}
	if err := validateContractGraphSource(source, graph, registryByOperation); err != nil {
		return bundleGenerationInput{}, err
	}
	projection, err := exactProjection(graph.Projections, detailProjectionID)
	if err != nil {
		return bundleGenerationInput{}, err
	}
	plan, err := validateDetailBundle(slices, projection.FieldNames, detailProjectionID)
	if err != nil {
		return bundleGenerationInput{}, err
	}
	gateway, err := exactGraphOperation(graph.Operations, gatewayOperationID)
	if err != nil {
		return bundleGenerationInput{}, err
	}
	for _, query := range queries {
		if err := validateGatewayOperation(gateway, query.entry); err != nil {
			return bundleGenerationInput{}, fmt.Errorf("operation %s: %w", query.entry.OperationName, err)
		}
	}

	var lock appLockDocument
	if err := decodeExactJSON(lockBytes, &lock); err != nil {
		return bundleGenerationInput{}, fmt.Errorf("decode App ContractGraph lock: %w", err)
	}
	if lock.Generator != "app-cloud-handoff" {
		return bundleGenerationInput{}, errors.New("App ContractGraph lock generator is not app-cloud-handoff")
	}
	if lock.ContractGraph.SHA256 != sha256Hex(graphBytes) || filepath.ToSlash(lock.ContractGraph.Path) != "quwoquan_service/generated/contract_graph.json" {
		return bundleGenerationInput{}, errors.New("App ContractGraph lock does not bind the exact generated ContractGraph")
	}
	ownerOperation, err := exactAppOperation(lock.AppExposedOperations, detailOperationID)
	if err != nil {
		return bundleGenerationInput{}, err
	}
	if ownerOperation.RequestEntity != "ContentPostDetailQuery" ||
		ownerOperation.ClientContract.ResponseType != "ContentPostDetailSlice" ||
		ownerOperation.ClientContract.ResponseDecoder != "decodeContentPostDetailSlice" ||
		len(ownerOperation.SurfaceIDs) == 0 {
		return bundleGenerationInput{}, errors.New("App lock ContentPostDetail client binding is incomplete or drifted")
	}
	expectedProjectionID := strings.Join([]string{"content", "post", ownerOperation.ClientContract.ResponseType}, ".")
	if plan.AssemblyProjectionID != expectedProjectionID {
		return bundleGenerationInput{}, fmt.Errorf("App lock response type requires assembly projection %s", expectedProjectionID)
	}
	sort.Strings(ownerOperation.SurfaceIDs)
	sort.Slice(queries, func(left, right int) bool {
		return queries[left].entry.OperationName < queries[right].entry.OperationName
	})
	if err := validateBundleSchemaTypes(schema, ownerOperation.ClientContract.ResponseType, projection.FieldNames, queries, plan); err != nil {
		return bundleGenerationInput{}, err
	}
	return bundleGenerationInput{
		registry: registry, queries: queries, plan: plan, gateway: gateway,
		ownerOperation: ownerOperation, projection: projection,
		registryDigest: sha256Hex(registryBytes), graphDigest: sha256Hex(graphBytes),
		appLockDigest: sha256Hex(lockBytes), schemaDigest: schemaDigest,
	}, nil
}

func registryHasCanonicalOperation(entries map[string]registryEntry, canonicalOperationID string) bool {
	for _, entry := range entries {
		if entry.CanonicalOperationID == canonicalOperationID {
			return true
		}
	}
	return false
}

func metadataDocumentPath(metadataPath, document string) (string, error) {
	if strings.TrimSpace(document) == "" || filepath.IsAbs(document) || strings.Contains(filepath.ToSlash(document), "../") {
		return "", errors.New("query metadata document path must stay below metadata root")
	}
	return filepath.Join(filepath.Dir(metadataPath), filepath.FromSlash(document)), nil
}

func bundleRootSelection(document *ast.QueryDocument, operation *ast.OperationDefinition) (string, string, []string, error) {
	fields, err := expandedFields(document, operation.SelectionSet, map[string]bool{})
	if err != nil {
		return "", "", nil, err
	}
	if len(fields) != 1 {
		return "", "", nil, errors.New("App persisted bundle query requires exactly one root field")
	}
	root := fields[0]
	responseKey := root.Alias
	if responseKey == "" {
		responseKey = root.Name
	}
	if responseKey != root.Name || len(root.Arguments) != 1 || root.Definition == nil || root.Definition.Type == nil {
		return "", "", nil, errors.New("bundle root must be unaliased, typed and use only postId")
	}
	postID := root.Arguments.ForName("postId")
	if postID == nil || postID.Value == nil || postID.Value.Kind != ast.Variable || postID.Value.Raw != "postId" {
		return "", "", nil, errors.New("bundle root must bind postId from $postId")
	}
	children, err := expandedFields(document, root.SelectionSet, map[string]bool{})
	if err != nil {
		return "", "", nil, err
	}
	selected := make([]string, 0, len(children))
	seen := map[string]bool{}
	for _, child := range children {
		if child.Alias != "" && child.Alias != child.Name {
			return "", "", nil, fmt.Errorf("bundle field %s must not be aliased", child.Name)
		}
		if seen[child.Name] {
			return "", "", nil, fmt.Errorf("bundle root contains duplicate field %s", child.Name)
		}
		seen[child.Name] = true
		selected = append(selected, child.Name)
	}
	sort.Strings(selected)
	return responseKey, root.Definition.Type.Name(), selected, nil
}
