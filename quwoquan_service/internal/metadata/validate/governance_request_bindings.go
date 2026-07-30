package validate

import (
	"regexp"
	"strings"

	"quwoquan_service/internal/metadata/ast"
)

var pathBindingPattern = regexp.MustCompile(`\{([^{}]+)\}`)

func validateRequestBindings(operation ast.Operation) []Issue {
	issues := validateRequestConstants(operation)
	if len(operation.LegacyRequestKeys) > 0 {
		issues = append(issues, issue(
			"CONTRACT.REQUEST_BINDING.LEGACY_SHAPE",
			operation.SourcePath,
			"operation %q uses legacy request binding keys %s; use request_bindings.path/query/header/injected and keep body on request_entity/request_body_kind",
			operation.ID,
			strings.Join(operation.LegacyRequestKeys, ", "),
		))
	}
	if len(operation.ClientBindingOverrides) > 0 {
		issues = append(issues, issue(
			"CONTRACT.REQUEST_BINDING.CLIENT_OWNED",
			operation.SourcePath,
			"operation %q declares client-owned binding keys %s; client bindings are derived from request_bindings",
			operation.ID,
			strings.Join(operation.ClientBindingOverrides, ", "),
		))
	}
	bindings := operation.RequestBindings
	if bindings == nil {
		if len(pathBindingPattern.FindAllStringSubmatch(operation.PathTemplate, -1)) > 0 {
			issues = append(issues, issue(
				"CONTRACT.REQUEST_BINDING.MISSING_PATH",
				operation.SourcePath,
				"operation %q path placeholders require canonical request_bindings.path entries",
				operation.ID,
			))
		}
		return issues
	}

	seenFields := map[string]string{}
	validateGroup := func(
		location string,
		values []ast.RequestBinding,
	) map[string]string {
		result := map[string]string{}
		for _, binding := range values {
			if binding.Name == "" || binding.Field == "" {
				issues = append(issues, issue(
					"CONTRACT.REQUEST_BINDING.INVALID",
					operation.SourcePath,
					"operation %q request_bindings.%s entries require name and field",
					operation.ID,
					location,
				))
				continue
			}
			if previous, exists := result[binding.Name]; exists {
				issues = append(issues, issue(
					"CONTRACT.REQUEST_BINDING.DUPLICATE_NAME",
					operation.SourcePath,
					"operation %q request_bindings.%s name %q maps to both %q and %q",
					operation.ID,
					location,
					binding.Name,
					previous,
					binding.Field,
				))
			} else {
				result[binding.Name] = binding.Field
			}
			if previous, exists := seenFields[binding.Field]; exists {
				issues = append(issues, issue(
					"CONTRACT.REQUEST_BINDING.FIELD_HAS_MULTIPLE_POSITIONS",
					operation.SourcePath,
					"operation %q request field %q is bound to both %s and %s",
					operation.ID,
					binding.Field,
					previous,
					location,
				))
			} else {
				seenFields[binding.Field] = location
			}
		}
		return result
	}

	pathBindings := validateGroup("path", bindings.Path)
	validateGroup("query", bindings.Query)
	validateGroup("header", bindings.Header)
	validateGroup("injected", bindings.Injected)

	pathNames := map[string]struct{}{}
	for _, match := range pathBindingPattern.FindAllStringSubmatch(
		operation.PathTemplate,
		-1,
	) {
		pathNames[strings.TrimSpace(match[1])] = struct{}{}
	}
	for name := range pathNames {
		if _, exists := pathBindings[name]; !exists {
			issues = append(issues, issue(
				"CONTRACT.REQUEST_BINDING.MISSING_PATH",
				operation.SourcePath,
				"operation %q path placeholder %q has no request_bindings.path entry",
				operation.ID,
				name,
			))
		}
	}
	for name := range pathBindings {
		if _, exists := pathNames[name]; !exists {
			issues = append(issues, issue(
				"CONTRACT.REQUEST_BINDING.ORPHAN_PATH",
				operation.SourcePath,
				"operation %q request_bindings.path name %q is not present in path %q",
				operation.ID,
				name,
				operation.PathTemplate,
			))
		}
	}
	for _, binding := range bindings.Path {
		if binding.Required != nil && !*binding.Required {
			issues = append(issues, issue(
				"CONTRACT.REQUEST_BINDING.OPTIONAL_PATH",
				operation.SourcePath,
				"operation %q path binding %q cannot be optional",
				operation.ID,
				binding.Name,
			))
		}
	}
	for _, binding := range bindings.Injected {
		if binding.Required != nil {
			issues = append(issues, issue(
				"CONTRACT.REQUEST_BINDING.INJECTED_REQUIREDNESS",
				operation.SourcePath,
				"operation %q injected binding %q must not declare wire requiredness",
				operation.ID,
				binding.Name,
			))
		}
	}
	for _, binding := range bindings.Header {
		switch strings.ToLower(strings.TrimSpace(binding.Name)) {
		case "authorization", "cookie", "idempotency-key", "x-request-id",
			"traceparent", "tracestate", "x-account-id", "x-persona-id":
			issues = append(issues, issue(
				"CONTRACT.REQUEST_BINDING.RESERVED_HEADER",
				operation.SourcePath,
				"operation %q header binding %q is runtime-owned and cannot be client supplied",
				operation.ID,
				binding.Name,
			))
		}
	}
	return issues
}

func validateRequestConstants(operation ast.Operation) []Issue {
	if operation.RequestConstants == nil {
		return nil
	}
	var issues []Issue
	if operation.RequestBodyKind != "object" {
		issues = append(issues, issue(
			"CONTRACT.REQUEST_CONSTANT.INVALID_BODY_KIND",
			operation.SourcePath,
			"operation %q request_constants.body requires request_body_kind=object",
			operation.ID,
		))
	}
	seen := map[string]struct{}{}
	for _, constant := range operation.RequestConstants.Body {
		name := strings.TrimSpace(constant.Name)
		if name == "" {
			issues = append(issues, issue(
				"CONTRACT.REQUEST_CONSTANT.INVALID_NAME",
				operation.SourcePath,
				"operation %q request_constants.body entries require a non-empty name",
				operation.ID,
			))
			continue
		}
		if _, exists := seen[name]; exists {
			issues = append(issues, issue(
				"CONTRACT.REQUEST_CONSTANT.DUPLICATE_NAME",
				operation.SourcePath,
				"operation %q repeats request_constants.body name %q",
				operation.ID,
				name,
			))
		}
		seen[name] = struct{}{}
		switch constant.Value.(type) {
		case nil, string, bool, int, int8, int16, int32, int64,
			uint, uint8, uint16, uint32, uint64, float32, float64:
		default:
			issues = append(issues, issue(
				"CONTRACT.REQUEST_CONSTANT.NON_SCALAR",
				operation.SourcePath,
				"operation %q request constant %q must be a JSON scalar",
				operation.ID,
				name,
			))
		}
	}
	if len(operation.RequestConstants.Body) == 0 {
		issues = append(issues, issue(
			"CONTRACT.REQUEST_CONSTANT.EMPTY",
			operation.SourcePath,
			"operation %q request_constants.body must not be empty",
			operation.ID,
		))
	}
	return issues
}
