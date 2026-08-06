package main

import (
	"fmt"
	"sort"
	"strings"

	"quwoquan_service/internal/metadata/ast"
	contractcodegen "quwoquan_service/internal/metadata/codegen"
)

const (
	hostAuthorityPersonaOperationID = "user.persona.EvaluatePersonaGatheringHostAuthority"
	hostAuthorityCircleOperationID  = "circle.circle.EvaluateCircleGatheringHostAuthority"
	hostAuthorityEntityOperationID  = "entity.homepage.EvaluateEntityHomepageGatheringHostAuthority"

	hostAuthorityUserFieldsPath       = "user/persona_management/persona/fields.yaml"
	hostAuthorityUserOperationsPath   = "user/persona_management/persona/operations.yaml"
	hostAuthorityCircleFieldsPath     = "circle/circle_management/circle/fields.yaml"
	hostAuthorityCircleOperationsPath = "circle/circle_management/circle/operations.yaml"
	hostAuthorityEntityFieldsPath     = "entity/entity_homepage/homepage/fields.yaml"
	hostAuthorityEntityOperationsPath = "entity/entity_homepage/homepage/operations.yaml"
)

type hostAuthorityField struct {
	Name string `yaml:"name"`
	Type string `yaml:"type"`
}

type hostAuthorityType struct {
	Fields []hostAuthorityField `yaml:"fields"`
}

type hostAuthorityFieldsDocument struct {
	Fields []hostAuthorityField         `yaml:"fields"`
	Types  map[string]hostAuthorityType `yaml:"types"`
}

type hostAuthorityOwnerClientModel struct {
	Persona ast.Operation
	Circle  ast.Operation
	Entity  ast.Operation
}

func generateHostAuthorityOwnerClient(
	source *contractcodegen.Source,
	outputPath string,
	check bool,
) (int, error) {
	model, err := buildHostAuthorityOwnerClientModel(source)
	if err != nil {
		return 0, err
	}
	if err := writeCanonicalGoOutput(
		outputPath,
		renderHostAuthorityOwnerClient(model),
		check,
	); err != nil {
		return 0, err
	}
	return 3, nil
}

func buildHostAuthorityOwnerClientModel(
	source *contractcodegen.Source,
) (hostAuthorityOwnerClientModel, error) {
	if source == nil || source.Graph() == nil {
		return hostAuthorityOwnerClientModel{}, fmt.Errorf("ContractGraph source is required")
	}
	operations := make(map[string]ast.Operation)
	for _, operation := range source.Graph().Operations {
		operations[operation.ID] = operation
	}
	requireOperation := func(
		operationID string,
		sourcePath string,
		requestEntity string,
		responseEntity string,
	) (ast.Operation, error) {
		operation, found := operations[operationID]
		if !found {
			return ast.Operation{}, fmt.Errorf(
				"ContractGraph has no canonical Host authority owner operation %s",
				operationID,
			)
		}
		if operation.SourcePath != sourcePath ||
			!strings.EqualFold(operation.Method, "POST") ||
			!strings.EqualFold(string(operation.Kind), "query") ||
			operation.RequestEntity != requestEntity ||
			operation.ResponseEntity != responseEntity {
			return ast.Operation{}, fmt.Errorf(
				"Host authority owner operation %s drifted from canonical POST query packet: source=%s method=%s kind=%s request=%s response=%s",
				operationID,
				operation.SourcePath,
				operation.Method,
				operation.Kind,
				operation.RequestEntity,
				operation.ResponseEntity,
			)
		}
		return operation, nil
	}

	persona, err := requireOperation(
		hostAuthorityPersonaOperationID,
		hostAuthorityUserOperationsPath,
		"PersonaGatheringHostAuthorityEvaluationQuery",
		"PersonaGatheringHostAuthorityEvidence",
	)
	if err != nil {
		return hostAuthorityOwnerClientModel{}, err
	}
	circle, err := requireOperation(
		hostAuthorityCircleOperationID,
		hostAuthorityCircleOperationsPath,
		"CircleGatheringHostAuthorityEvaluationQuery",
		"CircleGatheringHostAuthorityEvidence",
	)
	if err != nil {
		return hostAuthorityOwnerClientModel{}, err
	}
	entity, err := requireOperation(
		hostAuthorityEntityOperationID,
		hostAuthorityEntityOperationsPath,
		"EntityHomepageGatheringHostAuthorityEvaluationQuery",
		"EntityHomepageGatheringHostAuthorityEvidence",
	)
	if err != nil {
		return hostAuthorityOwnerClientModel{}, err
	}

	for path, requirements := range map[string]map[string]map[string]string{
		hostAuthorityUserFieldsPath: {
			"PersonaGatheringHostAuthorityEvaluationQuery": hostAuthorityQueryFieldTypes(),
			"PersonaGatheringHostAuthorityEvidence":        hostAuthorityEvidenceFieldTypes(),
		},
		hostAuthorityCircleFieldsPath: {
			"CircleGatheringHostAuthorityEvaluationQuery": hostAuthorityQueryFieldTypes(),
			"CircleGatheringHostAuthorityEvidence":        hostAuthorityEvidenceFieldTypes(),
		},
		hostAuthorityEntityFieldsPath: {
			"EntityHomepageGatheringHostAuthorityEvaluationQuery": hostAuthorityQueryFieldTypes(),
			"EntityHomepageGatheringHostAuthorityEvidence":        hostAuthorityEvidenceFieldTypes(),
		},
	} {
		if err := requireHostAuthorityFields(source, path, requirements); err != nil {
			return hostAuthorityOwnerClientModel{}, err
		}
	}
	return hostAuthorityOwnerClientModel{
		Persona: persona,
		Circle:  circle,
		Entity:  entity,
	}, nil
}

func hostAuthorityQueryFieldTypes() map[string]string {
	return map[string]string{
		"hostSubjectKind": "string", "hostSubjectId": "string",
		"hostSubjectRef": "string", "actorPersonaId": "string",
		"organizerPersonaId": "string", "authorityEvidenceRef": "string",
		"authorityVersion": "int64", "action": "string",
	}
}

func hostAuthorityEvidenceFieldTypes() map[string]string {
	fields := hostAuthorityQueryFieldTypes()
	fields["authorityDigest"] = "string"
	fields["expiresAt"] = "timestamp"
	fields["valid"] = "bool"
	fields["revoked"] = "bool"
	return fields
}

func requireHostAuthorityFields(
	source *contractcodegen.Source,
	path string,
	requirements map[string]map[string]string,
) error {
	var document hostAuthorityFieldsDocument
	if err := source.Decode(path, &document); err != nil {
		return fmt.Errorf("load %s: %w", path, err)
	}
	for typeName, requiredFields := range requirements {
		fields := document.Fields
		if typeName != "" {
			definition, found := document.Types[typeName]
			if !found {
				return fmt.Errorf("%s has no typed definition %s", path, typeName)
			}
			fields = definition.Fields
		}
		actual := make(map[string]string, len(fields))
		for _, field := range fields {
			actual[field.Name] = field.Type
		}
		names := make([]string, 0, len(requiredFields))
		for name := range requiredFields {
			names = append(names, name)
		}
		sort.Strings(names)
		for _, name := range names {
			if actual[name] != requiredFields[name] {
				return fmt.Errorf(
					"%s %s.%s type drift: got %q want %q",
					path,
					typeName,
					name,
					actual[name],
					requiredFields[name],
				)
			}
		}
	}
	return nil
}
