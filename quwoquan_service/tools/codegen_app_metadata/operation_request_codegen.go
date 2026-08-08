package main

import (
	"fmt"
	"path/filepath"
	"sort"
	"strings"
)

// operationRequestArtifact is the generated request ABI consumed by one
// GeneratedCloudOperationClient method. Request types are emitted as Dart part
// files owned by the existing response/contract library so domain enums and
// nested value objects remain in one library without an import cycle.
type operationRequestArtifact struct {
	RequestType string
	Encoder     string
}

type requestLibrarySpec struct {
	OwnerImport string
	Models      map[string]requestModelSpec
	// ProvidedModels are canonical wire value objects emitted by the owner
	// library. The request part may reference them, but must not redeclare them
	// as a second type in the same Dart library.
	ProvidedModels map[string]struct{}
	Operations     []requestOperationSpec
}

type requestModelSpec struct {
	Name           string
	Fields         []fieldDef
	ValidationKind string
	DerivedSource  string
	DerivedSHA256  string
	Pagination     *requestPaginationSpec
}

type requestPaginationSpec struct {
	Field        string
	DefaultItems int
	MaximumItems int
}

const (
	requestValidationProductOpsEventRecord = "product_ops_event_record"
	requestValidationRuntimeLogRecord      = "runtime_log_record"
)

type runtimeObservabilityEnvelope struct {
	Required            []string `yaml:"required"`
	Optional            []string `yaml:"optional"`
	ResourceRequired    []string `yaml:"resource_required"`
	ResourceOptional    []string `yaml:"resource_optional"`
	CorrelationOptional []string `yaml:"correlation_optional"`
}

type runtimeObservabilityKindFields struct {
	Required []string `yaml:"required"`
}

type runtimeObservabilityLimits struct {
	MaxBatchItems           int `yaml:"max_batch_items"`
	MaxMessageBytes         int `yaml:"max_message_bytes"`
	MaxAttributes           int `yaml:"max_attributes"`
	MaxAttributeKeyLength   int `yaml:"max_attribute_key_length"`
	MaxAttributeValueLength int `yaml:"max_attribute_value_length"`
}

type runtimeObservabilitySignal struct {
	ID                 string   `yaml:"id"`
	LogKind            string   `yaml:"log_kind"`
	AttributeAllowlist []string `yaml:"attribute_allowlist"`
	CorrelationKeys    []string `yaml:"correlation_keys"`
}

type runtimeObservabilityContract struct {
	Schema         string                                    `yaml:"schema"`
	LogKinds       []string                                  `yaml:"log_kinds"`
	SeverityLevels []string                                  `yaml:"severity_levels"`
	Envelope       runtimeObservabilityEnvelope              `yaml:"envelope"`
	KindFields     map[string]runtimeObservabilityKindFields `yaml:"kind_fields"`
	Limits         runtimeObservabilityLimits                `yaml:"limits"`
	Signals        []runtimeObservabilitySignal              `yaml:"signals"`
}

type productOpsTypedExtensionsContract struct {
	Catalog            string `yaml:"catalog"`
	Discriminator      string `yaml:"discriminator"`
	DefinitionsKey     string `yaml:"definitions_key"`
	RequiredByEventKey string `yaml:"required_by_event_key"`
	OptionalByEventKey string `yaml:"optional_by_event_key"`
	WireEncoding       string `yaml:"wire_encoding"`
	UnknownFieldPolicy string `yaml:"unknown_field_policy"`
}

type productOpsDerivedTypeDef struct {
	DerivedFrom string     `yaml:"derived_from"`
	Fields      []fieldDef `yaml:"fields"`
}

type productOpsIngestFieldsContract struct {
	Types           map[string]productOpsDerivedTypeDef `yaml:"types"`
	TypedExtensions productOpsTypedExtensionsContract   `yaml:"typed_extensions"`
}

type requestOperationSpec struct {
	CanonicalOperationID string
	RequestType          string
	RequestBodyKind      string
	RequestBindings      appRequestBindings
	RequestConstants     appRequestConstants
}

func writeGeneratedOperationRequests(
	appDir string,
	lock appContractLock,
	providedModelsByOwner map[string]map[string]struct{},
) (map[string]operationRequestArtifact, error) {
	libraries := map[string]*requestLibrarySpec{}
	artifacts := map[string]operationRequestArtifact{}
	clientOperationCount := 0
	for _, operation := range lock.AppExposedOperations {
		if operation.ClientContract != nil {
			clientOperationCount++
		}
	}
	if clientOperationCount == 0 {
		return nil, fmt.Errorf("empty-green: no App client operation")
	}
	enumValues, err := loadCanonicalRequestEnumValues()
	if err != nil {
		return nil, err
	}

	operations := append([]appExposedOperation(nil), lock.AppExposedOperations...)
	sort.Slice(operations, func(left, right int) bool {
		return operations[left].CanonicalOperationID <
			operations[right].CanonicalOperationID
	})
	for _, operation := range operations {
		client := operation.ClientContract
		if client == nil {
			continue
		}
		requestType := strings.TrimSpace(operation.RequestEntity)
		if requestType == "" {
			return nil, fmt.Errorf(
				"%s App client operation has no canonical request_entity",
				operation.CanonicalOperationID,
			)
		}
		bodyKind := strings.TrimSpace(operation.RequestBodyKind)
		if bodyKind != "object" && bodyKind != "none" {
			return nil, fmt.Errorf(
				"%s request_body_kind must be explicit object or none",
				operation.CanonicalOperationID,
			)
		}
		model, dependencies, err := loadOperationRequestModel(operation, requestType)
		if err != nil {
			return nil, err
		}
		if err := validateRequestModelCanonicalEnums(
			operation.CanonicalOperationID,
			model,
			enumValues,
		); err != nil {
			return nil, err
		}
		if err := validateRequestModelDefaults(
			operation.CanonicalOperationID,
			model,
		); err != nil {
			return nil, err
		}
		bindings := appRequestBindings{}
		if operation.RequestBindings != nil {
			bindings = *operation.RequestBindings
		}
		if err := validateRequestModelBindings(
			operation.CanonicalOperationID,
			model,
			bodyKind,
			bindings,
			operation.RequestConstants,
		); err != nil {
			return nil, err
		}
		if err := validateVersionPreconditionRequestContract(
			operation,
			model,
			bindings,
		); err != nil {
			return nil, err
		}
		clientModel := projectClientRequestModel(model, bindings)
		clientModel, err = applyOperationPaginationContract(
			operation.CanonicalOperationID,
			clientModel,
			bodyKind,
			bindings,
			operation.Pagination,
		)
		if err != nil {
			return nil, err
		}

		library := libraries[client.DartImport]
		if library == nil {
			library = &requestLibrarySpec{
				OwnerImport:    client.DartImport,
				Models:         map[string]requestModelSpec{},
				ProvidedModels: providedModelsByOwner[client.DartImport],
			}
			libraries[client.DartImport] = library
		}
		dependencyNames := make([]string, 0, len(dependencies))
		for name := range dependencies {
			dependencyNames = append(dependencyNames, name)
		}
		sort.Strings(dependencyNames)
		for _, name := range dependencyNames {
			dependency := dependencies[name]
			if err := validateRequestModelCanonicalEnums(
				operation.CanonicalOperationID,
				dependency,
				enumValues,
			); err != nil {
				return nil, err
			}
			if err := validateRequestModelDefaults(
				operation.CanonicalOperationID,
				dependency,
			); err != nil {
				return nil, err
			}
			if previous, exists := library.Models[name]; exists {
				if requestModelFingerprint(previous) != requestModelFingerprint(dependency) {
					return nil, fmt.Errorf(
						"%s reuses request value object %s with a different field contract",
						operation.CanonicalOperationID,
						name,
					)
				}
			} else {
				library.Models[name] = dependency
			}
		}
		if previous, exists := library.Models[requestType]; exists {
			if requestModelFingerprint(previous) != requestModelFingerprint(clientModel) {
				return nil, fmt.Errorf(
					"%s reuses request_entity %s with a different field contract",
					operation.CanonicalOperationID,
					requestType,
				)
			}
		} else {
			library.Models[requestType] = clientModel
		}
		constants := appRequestConstants{}
		if operation.RequestConstants != nil {
			constants = *operation.RequestConstants
		}
		library.Operations = append(library.Operations, requestOperationSpec{
			CanonicalOperationID: operation.CanonicalOperationID,
			RequestType:          requestType,
			RequestBodyKind:      bodyKind,
			RequestBindings:      bindings,
			RequestConstants:     constants,
		})
		artifacts[operation.CanonicalOperationID] = operationRequestArtifact{
			RequestType: requestType,
			Encoder: generatedOperationRequestEncoder(
				operation.CanonicalOperationID,
			),
		}
	}
	if len(artifacts) != clientOperationCount {
		return nil, fmt.Errorf(
			"request artifact coverage mismatch: clients=%d artifacts=%d",
			clientOperationCount,
			len(artifacts),
		)
	}

	imports := make([]string, 0, len(libraries))
	for ownerImport := range libraries {
		imports = append(imports, ownerImport)
	}
	sort.Strings(imports)
	for _, ownerImport := range imports {
		library := libraries[ownerImport]
		outputRelative, ownerRelative, err := requestPartPaths(ownerImport)
		if err != nil {
			return nil, err
		}
		outputPath := filepath.Join(
			appDir,
			"packages",
			"quwoquan_cloud_contracts",
			"lib",
			"src",
			filepath.FromSlash(outputRelative),
		)
		partOfURI, err := filepath.Rel(
			filepath.Dir(filepath.FromSlash(outputRelative)),
			filepath.FromSlash(ownerRelative),
		)
		if err != nil {
			return nil, fmt.Errorf("resolve request part owner: %w", err)
		}
		rendered, err := renderOperationRequestPart(
			*library,
			filepath.ToSlash(partOfURI),
			enumValues,
		)
		if err != nil {
			return nil, err
		}
		writeFile(outputPath, rendered)
	}
	return artifacts, nil
}
