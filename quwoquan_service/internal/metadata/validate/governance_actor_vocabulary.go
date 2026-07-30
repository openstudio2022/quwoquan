package validate

import (
	"regexp"
	"strings"

	"quwoquan_service/internal/metadata/ast"
	"quwoquan_service/internal/metadata/graph"
)

const legacyActorVocabularyIssue = "CONTRACT.ACTOR.LEGACY_SPLIT_PERSONA_TERM"

var legacyActiveActorTerm = regexp.MustCompile(
	`(?i)active[_-]?sub(?:id|envelope)?\b`,
)

func validateActorVocabulary(contractGraph *graph.ContractGraph) []Issue {
	var issues []Issue
	check := func(sourcePath, subject, value string) {
		if !containsLegacyActorTerm(value) {
			return
		}
		issues = append(issues, issue(
			legacyActorVocabularyIssue,
			sourcePath,
			"%s %q uses retired split actor vocabulary; use the canonical Persona term",
			subject,
			value,
		))
	}

	for _, object := range contractGraph.Objects {
		check(object.SourcePath, "object id", object.ID)
		check(object.SourcePath, "object name", object.Name)
		check(object.SourcePath, "object source path", object.SourcePath)
		for _, member := range object.Members {
			check(object.SourcePath, "member name", member.Name)
		}
	}
	for _, operation := range contractGraph.Operations {
		check(operation.SourcePath, "operation id", operation.ID)
		check(operation.SourcePath, "operation local id", operation.LocalID)
		check(operation.SourcePath, "operation path", operation.PathTemplate)
		check(operation.SourcePath, "operation facet", operation.Facet)
		check(operation.SourcePath, "operation method", operation.FacadeMethod)
		check(operation.SourcePath, "operation request entity", operation.RequestEntity)
		check(operation.SourcePath, "operation response entity", operation.ResponseEntity)
		check(operation.SourcePath, "operation response body", operation.ResponseBody)
		if operation.RequestBindings != nil {
			for _, bindings := range [][]struct {
				Name  string
				Field string
			}{
				requestBindingVocabulary(operation.RequestBindings.Path),
				requestBindingVocabulary(operation.RequestBindings.Query),
				requestBindingVocabulary(operation.RequestBindings.Injected),
			} {
				for _, binding := range bindings {
					check(operation.SourcePath, "request binding name", binding.Name)
					check(operation.SourcePath, "request binding field", binding.Field)
				}
			}
		}
		if client := operation.ClientContract; client != nil {
			check(operation.SourcePath, "client import", client.DartImport)
			check(operation.SourcePath, "client response type", client.ResponseType)
			check(operation.SourcePath, "client response decoder", client.ResponseDecoder)
		}
	}
	for _, projection := range contractGraph.Projections {
		check(projection.SourcePath, "projection id", projection.ID)
		check(projection.SourcePath, "projection read model", projection.ReadModel)
		check(projection.SourcePath, "projection Dart class", projection.DartClass)
		check(projection.SourcePath, "projection output path", projection.OutputPath)
		check(projection.SourcePath, "projection source path", projection.SourcePath)
		for _, field := range projection.FieldNames {
			check(projection.SourcePath, "projection field", field)
		}
	}
	for _, objectMap := range contractGraph.BusinessObjectMaps {
		for _, object := range objectMap.Objects {
			check(objectMap.SourcePath, "canonical object", object.CanonicalObject)
			for _, field := range object.Identity.Fields {
				check(objectMap.SourcePath, "identity field", field)
			}
			for role, fields := range object.FieldRoles {
				check(objectMap.SourcePath, "field role", role)
				for _, field := range fields {
					check(objectMap.SourcePath, "field role member", field)
				}
			}
		}
	}
	for _, field := range contractGraph.Governance.Fields {
		check(field.SourcePath, "field entity", field.Entity)
		check(field.SourcePath, "field name", field.Name)
		check(field.SourcePath, "field type", field.Type)
		check(field.SourcePath, "field enum ref", field.EnumRef)
	}
	for _, definition := range contractGraph.Governance.Types {
		check(definition.SourcePath, "type name", definition.Name)
	}
	for _, definition := range contractGraph.Governance.Enums {
		check(definition.SourcePath, "enum name", definition.Name)
	}
	for _, object := range contractGraph.Governance.Objects {
		for _, definition := range object.Errors {
			check(definition.SourcePath, "error code", definition.Code)
		}
		for _, definition := range object.Events {
			check(definition.SourcePath, "event name", definition.Name)
			check(definition.SourcePath, "event payload entity", definition.PayloadEntity)
			for _, field := range definition.PayloadFields {
				check(definition.SourcePath, "event payload field", field)
			}
		}
	}
	return issues
}

func containsLegacyActorTerm(value string) bool {
	if legacyActiveActorTerm.MatchString(value) {
		return true
	}
	normalized := strings.NewReplacer(
		"_", "",
		"-", "",
		" ", "",
		"/", "",
		".", "",
	).Replace(strings.ToLower(strings.TrimSpace(value)))
	return strings.Contains(normalized, "sub"+"account")
}

func requestBindingVocabulary(bindings []ast.RequestBinding) []struct {
	Name  string
	Field string
} {
	result := make([]struct {
		Name  string
		Field string
	}, 0, len(bindings))
	for _, binding := range bindings {
		result = append(result, struct {
			Name  string
			Field string
		}{Name: binding.Name, Field: binding.Field})
	}
	return result
}
