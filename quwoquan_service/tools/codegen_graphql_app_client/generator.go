package main

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"sort"
	"strings"

	"github.com/vektah/gqlparser/v2/ast"
	contractcodegen "quwoquan_service/internal/metadata/codegen"
	contractvalidate "quwoquan_service/internal/metadata/validate"
)

func Generate(options Options) ([]byte, []byte, error) {
	if strings.TrimSpace(options.MetadataDir) == "" {
		return nil, nil, errors.New("metadataDir is required")
	}
	source, err := contractcodegen.NewSource(options.MetadataDir, contractvalidate.ProfileBaseline)
	if err != nil {
		return nil, nil, fmt.Errorf("load ContractGraph Source: %w", err)
	}
	return generateWithSource(options, source)
}

func generateWithSource(options Options, source *contractcodegen.Source) ([]byte, []byte, error) {
	input, err := loadBundleGenerationInput(options, source)
	if err != nil {
		return nil, nil, err
	}
	generated := renderBundleDart(input)
	manifest := generatedManifest{
		Generator: appClientGenerator, RegistrySHA256: input.registryDigest,
		ContractGraphSHA256: input.graphDigest, AppLockSHA256: input.appLockDigest,
		Outputs: []generatedOutput{{
			Path:   appClientOutputPath,
			SHA256: sha256Hex(generated), Bytes: len(generated),
		}},
	}
	manifestBytes, err := json.MarshalIndent(manifest, "", "  ")
	if err != nil {
		return nil, nil, fmt.Errorf("encode generated manifest: %w", err)
	}
	return generated, append(manifestBytes, '\n'), nil
}

func validateDetailRegistryEntry(entry registryEntry) error {
	if !queryHashPattern.MatchString(entry.SHA256Hash) || !canonicalDigestPattern.MatchString(entry.CostPlanDigest) {
		return errors.New("ContentPostDetail registry hashes are not canonical")
	}
	if entry.OperationType != "query" || !strings.HasPrefix(entry.CanonicalOperationID, detailOperationID) ||
		len(entry.ObjectIDs) != 1 || entry.ObjectIDs[0] != "content.post" ||
		entry.CostModelVersion != "graphql-cost-v1" || entry.ExecutorKey != "content.post.getPost" {
		return errors.New("ContentPostDetail registry binding drifted")
	}
	if entry.AppClientBundle == nil || entry.AppClientBundle.BundleID != detailBundleID {
		return errors.New("ContentPostDetail signed registry App bundle binding is missing or belongs to another bundle")
	}
	if err := validateBundleBindingShape(*entry.AppClientBundle); err != nil {
		return fmt.Errorf("ContentPostDetail signed registry App bundle binding: %w", err)
	}
	if entry.Cost.Depth < 1 || entry.Cost.Depth > 5 || entry.Cost.TopLevelFields != 1 ||
		entry.Cost.Complexity < 1 || entry.Cost.Complexity > 1000 ||
		entry.Cost.VariablesMaxBytes < 1 || entry.Cost.PageSizeMax < 1 || entry.Cost.MaxOwnerCalls != 1 ||
		entry.Cost.MaxBatchKeys != 1 || entry.Cost.MaxResponseBytes < 1 || entry.Cost.SLORef == "" {
		return errors.New("ContentPostDetail registry cost binding is incomplete")
	}
	if entry.CostPlan.BaseComplexity < 1 ||
		entry.CostPlan.MaxOwnerCalls != entry.Cost.MaxOwnerCalls ||
		entry.CostPlan.MaxBatchKeys != entry.Cost.MaxBatchKeys ||
		entry.CostPlan.MaxResponseBytes != entry.Cost.MaxResponseBytes {
		return errors.New("ContentPostDetail computed costPlan is inconsistent")
	}
	if err := validatePaginationCostPlan(entry); err != nil {
		return err
	}
	encodedPlan, err := json.Marshal(entry.CostPlan)
	if err != nil {
		return fmt.Errorf("encode ContentPostDetail costPlan: %w", err)
	}
	if entry.CostPlanDigest != "sha256:"+sha256Hex(encodedPlan) {
		return errors.New("ContentPostDetail costPlanDigest differs from computed costPlan")
	}
	return nil
}

func validatePaginationCostPlan(entry registryEntry) error {
	if err := validateSortedUniqueStrings(entry.PaginationVariables, "paginationVariables"); err != nil {
		return err
	}
	if len(entry.PaginationVariables) != len(entry.CostPlan.ListMultipliers) {
		return errors.New("ContentPostDetail pagination variables and cost multipliers differ")
	}
	maximumPageSize := 1
	for index, multiplier := range entry.CostPlan.ListMultipliers {
		if multiplier.VariablePath != entry.PaginationVariables[index] || multiplier.Coefficient < 1 ||
			multiplier.DefaultValue < 1 || multiplier.MaximumValue < multiplier.DefaultValue {
			return errors.New("ContentPostDetail pagination cost multiplier is invalid or unordered")
		}
		if multiplier.MaximumValue > maximumPageSize {
			maximumPageSize = multiplier.MaximumValue
		}
	}
	if entry.Cost.PageSizeMax != maximumPageSize {
		return errors.New("ContentPostDetail pageSizeMax differs from signed cost multipliers")
	}
	return nil
}

func exactMetadataEntry(document queryMetadataDocument, registry registryEntry) (queryMetadataEntry, error) {
	if document.Schema != "graphql-read-query-metadata" {
		return queryMetadataEntry{}, errors.New("query metadata schema identity drifted")
	}
	var matches []queryMetadataEntry
	for _, entry := range document.Entries {
		if entry.CanonicalOperationID == registry.CanonicalOperationID {
			matches = append(matches, entry)
		}
	}
	if len(matches) != 1 || strings.TrimSpace(matches[0].Document) == "" {
		return queryMetadataEntry{}, errors.New("query metadata and registry binding differ")
	}
	metadata := matches[0]
	if !containsString([]string{"collection", "detail", "page_composite"}, metadata.QueryClass) ||
		metadata.VariablesMaxBytes != registry.Cost.VariablesMaxBytes ||
		metadata.MaxOwnerCalls != registry.Cost.MaxOwnerCalls || metadata.MaxBatchKeys != registry.Cost.MaxBatchKeys ||
		metadata.MaxResponseBytes != registry.Cost.MaxResponseBytes || metadata.SLORef != registry.Cost.SLORef ||
		metadata.ExecutorKey != registry.ExecutorKey {
		return queryMetadataEntry{}, errors.New("query metadata cost and executor binding differs from registry")
	}
	if filepath.IsAbs(metadata.Document) || strings.Contains(filepath.ToSlash(metadata.Document), "../") {
		return queryMetadataEntry{}, errors.New("query metadata document path must stay below metadata root")
	}
	return metadata, nil
}

func validateDetailVariables(operation *ast.OperationDefinition, entry registryEntry) error {
	if len(operation.VariableDefinitions) != 1+len(entry.PaginationVariables) {
		return errors.New("ContentPostDetail query variables differ from signed registry cost plan")
	}
	postID := operation.VariableDefinitions.ForName("postId")
	if postID == nil || postID.Type == nil || postID.Type.String() != "ID!" || postID.DefaultValue != nil {
		return errors.New("ContentPostDetail $postId must be a required ID without a default")
	}
	for index, variableName := range entry.PaginationVariables {
		definition := operation.VariableDefinitions.ForName(variableName)
		multiplier := entry.CostPlan.ListMultipliers[index]
		if definition == nil || definition.Type == nil || definition.Type.String() != "Int!" ||
			definition.DefaultValue == nil || definition.DefaultValue.Kind != ast.IntValue ||
			definition.DefaultValue.Raw != fmt.Sprintf("%d", multiplier.DefaultValue) ||
			multiplier.DefaultValue != multiplier.MaximumValue {
			return fmt.Errorf("ContentPostDetail pagination variable $%s must use its signed maximum as the required default", variableName)
		}
	}
	return nil
}

func expandedFields(document *ast.QueryDocument, selections ast.SelectionSet, visiting map[string]bool) ([]*ast.Field, error) {
	var fields []*ast.Field
	for _, selection := range selections {
		switch current := selection.(type) {
		case *ast.Field:
			if len(current.Directives) != 0 {
				return nil, fmt.Errorf("conditional/directive field %s is forbidden in the generated detail view", current.Name)
			}
			fields = append(fields, current)
		case *ast.InlineFragment:
			if len(current.Directives) != 0 {
				return nil, errors.New("conditional/directive inline fragments are forbidden in the generated detail view")
			}
			nested, err := expandedFields(document, current.SelectionSet, visiting)
			if err != nil {
				return nil, err
			}
			fields = append(fields, nested...)
		case *ast.FragmentSpread:
			if len(current.Directives) != 0 || visiting[current.Name] {
				return nil, fmt.Errorf("conditional/directive or cyclic fragment %s is forbidden", current.Name)
			}
			fragment := document.Fragments.ForName(current.Name)
			if fragment == nil || len(fragment.Directives) != 0 {
				return nil, fmt.Errorf("fragment %s is missing or directive-bound", current.Name)
			}
			visiting[current.Name] = true
			nested, err := expandedFields(document, fragment.SelectionSet, visiting)
			delete(visiting, current.Name)
			if err != nil {
				return nil, err
			}
			fields = append(fields, nested...)
		default:
			return nil, fmt.Errorf("unsupported GraphQL selection %T", selection)
		}
	}
	return fields, nil
}

func exactProjection(projections []graphProjection, id string) (graphProjection, error) {
	for _, projection := range projections {
		if projection.ID == id && len(projection.FieldNames) != 0 {
			return projection, nil
		}
	}
	return graphProjection{}, fmt.Errorf("ContractGraph projection %s is missing", id)
}

func missingFields(required []string, selected map[string]bool) []string {
	missing := make([]string, 0)
	for _, field := range required {
		if !selected[field] {
			missing = append(missing, field)
		}
	}
	sort.Strings(missing)
	return missing
}

func extraFields(required []string, selected map[string]bool) []string {
	allowed := make(map[string]bool, len(required))
	for _, field := range required {
		allowed[field] = true
	}
	extra := make([]string, 0)
	for field := range selected {
		if !allowed[field] {
			extra = append(extra, field)
		}
	}
	sort.Strings(extra)
	return extra
}

func exactGraphOperation(operations []graphOperation, id string) (graphOperation, error) {
	for _, operation := range operations {
		if operation.ID == id {
			return operation, nil
		}
	}
	return graphOperation{}, fmt.Errorf("ContractGraph operation %s is missing", id)
}

func validateGatewayOperation(operation graphOperation, entry registryEntry) error {
	if operation.Method != "POST" || operation.PathTemplate != "/graphql" || operation.Kind != "query" ||
		operation.AuthMode != "optional" || operation.ActorRequirement != "none" ||
		operation.RequestEntity != "PersistedGraphQLRequest" || operation.RequestBodyKind != "object" ||
		operation.Transport != "json" || operation.ResponseEntity != "GraphQLReadResponse" ||
		operation.ResponseBodyKind != "object" || operation.Reliability.TimeoutMilliseconds <= 0 ||
		operation.Reliability.RetryMode != "idempotent" || operation.Reliability.MaxAttempts <= 0 ||
		len(operation.ErrorCodes) == 0 {
		return errors.New("GraphQL transport operation is incomplete or drifted")
	}
	if operation.ResponseAdmission.MaximumBodyBytes <= entry.Cost.MaxResponseBytes {
		return errors.New("GraphQL transport response admission must exceed signed data byte budget for the envelope")
	}
	return nil
}

func exactAppOperation(operations []appLockOperation, id string) (appLockOperation, error) {
	for _, operation := range operations {
		if operation.CanonicalOperationID == id {
			return operation, nil
		}
	}
	return appLockOperation{}, fmt.Errorf("App lock operation %s is missing", id)
}

func readRegularFile(path, label string) ([]byte, error) {
	info, err := os.Lstat(path)
	if err != nil {
		return nil, fmt.Errorf("inspect %s: %w", label, err)
	}
	if !info.Mode().IsRegular() {
		return nil, fmt.Errorf("%s must be a regular file", label)
	}
	file, err := os.Open(path)
	if err != nil {
		return nil, fmt.Errorf("open %s: %w", label, err)
	}
	defer file.Close()
	payload, err := io.ReadAll(file)
	if err != nil {
		return nil, fmt.Errorf("read %s: %w", label, err)
	}
	return payload, nil
}

func decodeExactJSON(payload []byte, target any) error {
	decoder := json.NewDecoder(bytes.NewReader(payload))
	if err := decoder.Decode(target); err != nil {
		return err
	}
	var trailing any
	if err := decoder.Decode(&trailing); !errors.Is(err, io.EOF) {
		return errors.New("JSON must contain exactly one value")
	}
	return nil
}
