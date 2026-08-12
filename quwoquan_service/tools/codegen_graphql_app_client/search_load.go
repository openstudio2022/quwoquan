package main

import (
	"encoding/json"
	"errors"
	"fmt"
	"path/filepath"
	"reflect"
	"sort"
	"strings"

	"github.com/vektah/gqlparser/v2"
	"github.com/vektah/gqlparser/v2/ast"
	metadataast "quwoquan_service/internal/metadata/ast"
	contractcodegen "quwoquan_service/internal/metadata/codegen"
)

func loadSearchGenerationInput(options Options, source *contractcodegen.Source) (searchGenerationInput, error) {
	registryBytes, err := readRegularFile(options.RegistryPath, "persisted query registry")
	if err != nil {
		return searchGenerationInput{}, err
	}
	metadataBytes, err := readRegularFile(options.MetadataPath, "query metadata")
	if err != nil {
		return searchGenerationInput{}, err
	}
	schemaPath := options.SchemaPath
	if strings.TrimSpace(schemaPath) == "" {
		schemaPath = filepath.Join(filepath.Dir(options.MetadataPath), "schema.graphqls")
	}
	schemaBytes, err := readRegularFile(schemaPath, "GraphQL read schema")
	if err != nil {
		return searchGenerationInput{}, err
	}
	graphBytes, err := readRegularFile(options.ContractGraphPath, "ContractGraph")
	if err != nil {
		return searchGenerationInput{}, err
	}
	lockBytes, err := readRegularFile(options.AppLockPath, "App ContractGraph lock")
	if err != nil {
		return searchGenerationInput{}, err
	}

	var registry registryDocument
	if err := decodeExactJSON(registryBytes, &registry); err != nil {
		return searchGenerationInput{}, fmt.Errorf("decode persisted query registry: %w", err)
	}
	if !canonicalDigestPattern.MatchString(registry.CandidateDigest) || !canonicalDigestPattern.MatchString(registry.SchemaDigest) {
		return searchGenerationInput{}, errors.New("persisted query registry digests are not canonical sha256")
	}
	schemaDigest := "sha256:" + sha256Hex(schemaBytes)
	if registry.SchemaDigest != schemaDigest {
		return searchGenerationInput{}, errors.New("GraphQL schema digest differs from signed registry")
	}
	entry, err := exactSearchRegistryEntry(registry.Entries)
	if err != nil {
		return searchGenerationInput{}, err
	}
	if err := validateSearchRegistryEntry(entry); err != nil {
		return searchGenerationInput{}, err
	}

	var metadata queryMetadataDocument
	if err := decodeExactJSON(metadataBytes, &metadata); err != nil {
		return searchGenerationInput{}, fmt.Errorf("decode query metadata: %w", err)
	}
	metadataEntry, err := exactMetadataEntry(metadata, entry)
	if err != nil {
		return searchGenerationInput{}, err
	}
	if metadataEntry.QueryClass != "page_composite" {
		return searchGenerationInput{}, errors.New("SearchPage query metadata must be page_composite")
	}
	documentPath, err := metadataDocumentPath(options.MetadataPath, metadataEntry.Document)
	if err != nil {
		return searchGenerationInput{}, err
	}
	documentBytes, err := readRegularFile(documentPath, "SearchPage persisted GraphQL document")
	if err != nil {
		return searchGenerationInput{}, err
	}
	if sha256Hex(documentBytes) != entry.SHA256Hash {
		return searchGenerationInput{}, errors.New("SearchPage document hash differs from signed registry")
	}
	schema, schemaError := gqlparser.LoadSchema(&ast.Source{Name: schemaPath, Input: string(schemaBytes)})
	if schemaError != nil {
		return searchGenerationInput{}, fmt.Errorf("load GraphQL read schema: %w", schemaError)
	}
	document, queryError := gqlparser.LoadQuery(schema, string(documentBytes))
	if queryError != nil {
		return searchGenerationInput{}, fmt.Errorf("load SearchPage persisted GraphQL document: %w", queryError)
	}
	operation, responseKey, inputType, responseType, selectedFields, err := validateSearchDocument(document, entry)
	if err != nil {
		return searchGenerationInput{}, err
	}
	_ = operation
	if err := validateSearchInputExposure(schema, inputType); err != nil {
		return searchGenerationInput{}, err
	}

	var graph contractGraphDocument
	if err := decodeExactJSON(graphBytes, &graph); err != nil {
		return searchGenerationInput{}, fmt.Errorf("decode ContractGraph: %w", err)
	}
	searchOperation, err := exactGraphOperation(graph.Operations, searchPageOperationID)
	if err != nil {
		return searchGenerationInput{}, err
	}
	gateway, err := exactGraphOperation(graph.Operations, gatewayOperationID)
	if err != nil {
		return searchGenerationInput{}, err
	}
	if err := validateGatewayOperation(gateway, entry); err != nil {
		return searchGenerationInput{}, err
	}

	var lock appLockDocument
	if err := decodeExactJSON(lockBytes, &lock); err != nil {
		return searchGenerationInput{}, fmt.Errorf("decode App ContractGraph lock: %w", err)
	}
	if lock.Generator != "app-cloud-handoff" {
		return searchGenerationInput{}, errors.New("App ContractGraph lock generator is not app-cloud-handoff")
	}
	if lock.ContractGraph.SHA256 != sha256Hex(graphBytes) || filepath.ToSlash(lock.ContractGraph.Path) != "quwoquan_service/generated/contract_graph.json" {
		return searchGenerationInput{}, errors.New("App ContractGraph lock does not bind the exact generated ContractGraph")
	}
	appOperation, err := exactAppOperation(lock.AppExposedOperations, searchPageOperationID)
	if err != nil {
		return searchGenerationInput{}, err
	}
	if appOperation.RequestEntity != inputType {
		return searchGenerationInput{}, fmt.Errorf("App lock request type differs from persisted $input type %s", inputType)
	}
	if strings.TrimSpace(appOperation.ClientContract.ResponseType) == "" ||
		appOperation.ClientContract.ResponseDecoder != "decode"+appOperation.ClientContract.ResponseType ||
		len(appOperation.SurfaceIDs) == 0 {
		return searchGenerationInput{}, errors.New("App lock SearchPage client binding is incomplete or drifted")
	}
	if appOperation.ClientContract.ResponseType != responseType {
		return searchGenerationInput{}, fmt.Errorf("App lock response type differs from persisted SearchPage root type %s", responseType)
	}
	if searchOperation.RequestEntity != inputType || searchOperation.ResponseEntity != appOperation.ClientContract.ResponseType ||
		searchOperation.Kind != "query" {
		return searchGenerationInput{}, errors.New("ContractGraph SearchPage request/response binding differs from schema and App lock")
	}
	wireDocument, responseFields, err := exactSearchWireFields(
		graph.Documents, searchOperation.SourcePath, inputType, responseType,
	)
	if err != nil {
		return searchGenerationInput{}, err
	}
	if !equalSortedStrings(responseFields, selectedFields) {
		return searchGenerationInput{}, errors.New("SearchPage schema-owned response fields differ from persisted selection")
	}
	if err := validateSearchContractGraphSource(source, graph, wireDocument); err != nil {
		return searchGenerationInput{}, err
	}
	sort.Strings(appOperation.SurfaceIDs)
	return searchGenerationInput{
		registry: registry, entry: entry, metadata: metadataEntry,
		responseKey: responseKey, inputType: inputType, responseType: responseType, selectedFields: selectedFields,
		gateway: gateway, operation: searchOperation, appOperation: appOperation, wireDocument: wireDocument,
		registryDigest: sha256Hex(registryBytes), graphDigest: sha256Hex(graphBytes),
		appLockDigest: sha256Hex(lockBytes), schemaDigest: schemaDigest,
	}, nil
}

func exactSearchRegistryEntry(entries []registryEntry) (registryEntry, error) {
	matches := make([]registryEntry, 0, 1)
	for _, entry := range entries {
		if entry.CanonicalOperationID == searchPageOperationID || entry.OperationName == searchPageOperationName {
			matches = append(matches, entry)
		}
	}
	if len(matches) != 1 || matches[0].CanonicalOperationID != searchPageOperationID || matches[0].OperationName != searchPageOperationName {
		return registryEntry{}, errors.New("signed registry must contain exactly one signed SearchPage entry")
	}
	return matches[0], nil
}

func validateSearchRegistryEntry(entry registryEntry) error {
	if !queryHashPattern.MatchString(entry.SHA256Hash) || !canonicalDigestPattern.MatchString(entry.CostPlanDigest) {
		return errors.New("SearchPage registry hashes are not canonical")
	}
	if entry.OperationType != "query" || len(entry.ObjectIDs) != 1 || entry.ObjectIDs[0] != "gateway.persisted_query_execution" ||
		entry.CostModelVersion != "graphql-cost-v1" || strings.TrimSpace(entry.ExecutorKey) == "" {
		return errors.New("SearchPage signed registry identity is incomplete or drifted")
	}
	if entry.Authorization.Principal != "public" || len(entry.Authorization.Scopes) != 0 ||
		strings.TrimSpace(entry.Authorization.OwnershipPolicy) == "" {
		return errors.New("SearchPage signed public authorization binding is incomplete or drifted")
	}
	if entry.Cost.Depth < 1 || entry.Cost.Depth > 5 || entry.Cost.TopLevelFields != 1 ||
		entry.Cost.Complexity < 1 || entry.Cost.Complexity > 500 || entry.Cost.VariablesMaxBytes < 1 ||
		entry.Cost.MaxOwnerCalls != 1 || entry.Cost.MaxBatchKeys < 1 || entry.Cost.MaxResponseBytes < 1 ||
		strings.TrimSpace(entry.Cost.SLORef) == "" {
		return errors.New("SearchPage signed page-composite cost binding is incomplete or exceeds its regular budget")
	}
	if entry.CostPlan.BaseComplexity < 1 || entry.CostPlan.MaxOwnerCalls != entry.Cost.MaxOwnerCalls ||
		entry.CostPlan.MaxBatchKeys != entry.Cost.MaxBatchKeys || entry.CostPlan.MaxResponseBytes != entry.Cost.MaxResponseBytes {
		return errors.New("SearchPage computed costPlan is inconsistent")
	}
	if err := validateSearchPaginationCostPlan(entry); err != nil {
		return err
	}
	encodedPlan, err := json.Marshal(entry.CostPlan)
	if err != nil {
		return fmt.Errorf("encode SearchPage costPlan: %w", err)
	}
	if entry.CostPlanDigest != "sha256:"+sha256Hex(encodedPlan) {
		return errors.New("SearchPage costPlanDigest differs from computed costPlan")
	}
	return nil
}

func validateSearchPaginationCostPlan(entry registryEntry) error {
	if err := validateSortedUniqueStrings(entry.PaginationVariables, "SearchPage paginationVariables"); err != nil {
		return err
	}
	if len(entry.PaginationVariables) != len(entry.CostPlan.ListMultipliers) {
		return errors.New("SearchPage pagination variables and cost multipliers differ")
	}
	maximumPageSize := 1
	for index, multiplier := range entry.CostPlan.ListMultipliers {
		if multiplier.VariablePath != entry.PaginationVariables[index] || multiplier.Coefficient < 1 ||
			multiplier.DefaultValue < 1 || multiplier.MaximumValue < multiplier.DefaultValue ||
			!strings.HasPrefix(multiplier.VariablePath, "input.") {
			return errors.New("SearchPage pagination cost multiplier is invalid or unordered")
		}
		if multiplier.MaximumValue > maximumPageSize {
			maximumPageSize = multiplier.MaximumValue
		}
	}
	if entry.Cost.PageSizeMax != maximumPageSize {
		return errors.New("SearchPage pageSizeMax differs from signed cost multipliers")
	}
	return nil
}

func validateSearchDocument(document *ast.QueryDocument, entry registryEntry) (*ast.OperationDefinition, string, string, string, []string, error) {
	if len(document.Operations) != 1 || document.Operations[0].Name != searchPageOperationName || document.Operations[0].Operation != ast.Query {
		return nil, "", "", "", nil, errors.New("persisted document must contain exactly one signed SearchPage query")
	}
	operation := document.Operations[0]
	if len(operation.VariableDefinitions) != 1 {
		return nil, "", "", "", nil, errors.New("SearchPage must declare only $input")
	}
	input := operation.VariableDefinitions.ForName("input")
	if input == nil || input.Type == nil || input.Type.NamedType != searchPageInputType || !input.Type.NonNull || input.DefaultValue != nil {
		return nil, "", "", "", nil, errors.New("SearchPage $input must be required SearchPageInput without a default")
	}
	fields, err := expandedFields(document, operation.SelectionSet, map[string]bool{})
	if err != nil {
		return nil, "", "", "", nil, err
	}
	if len(fields) != 1 {
		return nil, "", "", "", nil, errors.New("SearchPage requires exactly one root field")
	}
	root := fields[0]
	if root.Name != searchPageRootField || root.Alias != root.Name || root.Definition == nil || root.Definition.Type == nil {
		return nil, "", "", "", nil, errors.New("SearchPage root must be unaliased searchPage")
	}
	if len(root.Arguments) != 1 {
		return nil, "", "", "", nil, errors.New("SearchPage root must bind only input")
	}
	argument := root.Arguments.ForName("input")
	if argument == nil || argument.Value == nil || argument.Value.Kind != ast.Variable || argument.Value.Raw != "input" {
		return nil, "", "", "", nil, errors.New("SearchPage root must bind input from $input")
	}
	children, err := expandedFields(document, root.SelectionSet, map[string]bool{})
	if err != nil {
		return nil, "", "", "", nil, err
	}
	selected := make([]string, 0, len(children))
	seen := map[string]bool{}
	for _, child := range children {
		if child.Alias != child.Name || seen[child.Name] {
			return nil, "", "", "", nil, errors.New("SearchPage response fields must be unaliased and unique")
		}
		seen[child.Name] = true
		selected = append(selected, child.Name)
	}
	if len(selected) == 0 {
		return nil, "", "", "", nil, errors.New("SearchPage response selection is empty")
	}
	sort.Strings(selected)
	return operation, searchPageRootField, input.Type.NamedType, root.Definition.Type.Name(), selected, nil
}

func validateSearchInputExposure(schema *ast.Schema, inputType string) error {
	definition := schema.Types[inputType]
	if definition == nil || definition.Kind != ast.InputObject {
		return errors.New("SearchPageInput must be a schema input object")
	}
	mode := definition.Fields.ForName("mode")
	if mode == nil {
		return nil
	}
	modeDefinition := schema.Types[mode.Type.Name()]
	if modeDefinition == nil || modeDefinition.Kind != ast.Enum {
		return errors.New("SearchPageInput.mode must be a closed enum when exposed to the public App")
	}
	for _, value := range modeDefinition.EnumValues {
		if strings.EqualFold(value.Name, "retrieval") {
			return errors.New("SearchPageInput must not expose trusted retrieval mode to the public App")
		}
	}
	return nil
}

func exactSearchWireFields(
	documents []graphDocument,
	operationSourcePath string,
	inputType string,
	responseType string,
) (graphDocument, []string, error) {
	contextDirectory := filepath.Dir(filepath.ToSlash(operationSourcePath))
	wirePath := filepath.Join(contextDirectory, "fields.yaml")
	matches := make([]graphDocument, 0, 1)
	for _, document := range documents {
		if filepath.ToSlash(document.Path) == filepath.ToSlash(wirePath) {
			matches = append(matches, document)
		}
	}
	if len(matches) != 1 || !queryHashPattern.MatchString(matches[0].SHA256) {
		return graphDocument{}, nil, fmt.Errorf("ContractGraph must contain exact schema-owned wire document %s", wirePath)
	}
	var wire struct {
		Types map[string]struct {
			Fields []struct {
				Name string `json:"name"`
			} `json:"fields"`
		} `json:"types"`
	}
	if err := decodeExactJSON(matches[0].Content, &wire); err != nil {
		return graphDocument{}, nil, fmt.Errorf("decode ContractGraph SearchPage wire document: %w", err)
	}
	input, inputPresent := wire.Types[inputType]
	response, responsePresent := wire.Types[responseType]
	if !inputPresent || !responsePresent {
		return graphDocument{}, nil, errors.New("SearchPage App input/response types are absent from schema-owned wire document")
	}
	if err := validateSearchWireFieldNames(input.Fields, inputType); err != nil {
		return graphDocument{}, nil, err
	}
	if err := validateSearchWireFieldNames(response.Fields, responseType); err != nil {
		return graphDocument{}, nil, err
	}
	fields := make([]string, 0, len(response.Fields))
	for _, field := range response.Fields {
		fields = append(fields, field.Name)
	}
	return matches[0], fields, nil
}

func validateSearchWireFieldNames(fields []struct {
	Name string `json:"name"`
}, typeName string) error {
	if len(fields) == 0 {
		return fmt.Errorf("SearchPage schema-owned type %s has no fields", typeName)
	}
	seen := map[string]bool{}
	for _, field := range fields {
		if strings.TrimSpace(field.Name) == "" || seen[field.Name] {
			return fmt.Errorf("SearchPage schema-owned type %s has blank or duplicate fields", typeName)
		}
		seen[field.Name] = true
	}
	return nil
}

func validateSearchContractGraphSource(source *contractcodegen.Source, graph contractGraphDocument, wireDocument graphDocument) error {
	if source == nil || source.Graph() == nil {
		return errors.New("ContractGraph Source is required")
	}
	for _, operationID := range []string{gatewayOperationID, searchPageOperationID} {
		generated, err := exactGraphOperation(graph.Operations, operationID)
		if err != nil {
			return err
		}
		matches := make([]metadataast.Operation, 0, 1)
		for _, candidate := range source.Graph().Operations {
			if candidate.ID == operationID {
				matches = append(matches, candidate)
			}
		}
		if len(matches) != 1 {
			return fmt.Errorf("ContractGraph Source must contain exactly one %s operation; got %d", operationID, len(matches))
		}
		if string(matches[0].Kind) != generated.Kind || matches[0].ObjectID != generated.ObjectID ||
			matches[0].Method != generated.Method || matches[0].PathTemplate != generated.PathTemplate ||
			matches[0].RequestEntity != generated.RequestEntity || matches[0].ResponseEntity != generated.ResponseEntity ||
			sourceMaximumBodyBytes(matches[0]) != generated.ResponseAdmission.MaximumBodyBytes {
			return fmt.Errorf(
				"generated ContractGraph operation %s differs from ContractGraph Source: source kind=%s object=%s method=%s path=%s request=%s response=%s maxBody=%d; generated kind=%s object=%s method=%s path=%s request=%s response=%s maxBody=%d",
				operationID,
				matches[0].Kind, matches[0].ObjectID, matches[0].Method, matches[0].PathTemplate,
				matches[0].RequestEntity, matches[0].ResponseEntity, sourceMaximumBodyBytes(matches[0]),
				generated.Kind, generated.ObjectID, generated.Method, generated.PathTemplate,
				generated.RequestEntity, generated.ResponseEntity, generated.ResponseAdmission.MaximumBodyBytes,
			)
		}
	}
	documentMatches := 0
	for _, candidate := range source.Graph().Documents {
		if candidate.Path == wireDocument.Path && candidate.SHA256 == wireDocument.SHA256 {
			documentMatches++
		}
	}
	if documentMatches != 1 {
		return errors.New("generated SearchPage wire document differs from ContractGraph Source")
	}
	return nil
}

func equalSortedStrings(left, right []string) bool {
	leftCopy := append([]string(nil), left...)
	rightCopy := append([]string(nil), right...)
	sort.Strings(leftCopy)
	sort.Strings(rightCopy)
	return reflect.DeepEqual(leftCopy, rightCopy)
}
