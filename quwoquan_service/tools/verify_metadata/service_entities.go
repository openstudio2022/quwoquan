package main

import (
	"fmt"
	"path/filepath"
	"sort"
	"strings"

	"gopkg.in/yaml.v3"
)

// responseBodyKinds 是 operation 响应体形态闭集：
//
//	object = 单读模型对象；page = 分页/列表（items 承载读模型）；ack = 仅状态确认（无读模型）。
var responseBodyKinds = map[string]bool{
	"object":  true,
	"page":    true,
	"ack":     true,
	"upgrade": true,
}
var requestBodyKinds = map[string]bool{"object": true, "none": true}

type requestInvocationField struct {
	Name string `yaml:"name"`
}

type requestInvocationEntity struct {
	Fields []requestInvocationField `yaml:"fields"`
}

type requestInvocationFieldsDocument struct {
	Entity       string                             `yaml:"entity"`
	Fields       []requestInvocationField           `yaml:"fields"`
	Entities     map[string]requestInvocationEntity `yaml:"entities"`
	Types        map[string]requestInvocationEntity `yaml:"types"`
	ValueObjects map[string]requestInvocationEntity `yaml:"value_objects"`
	Members      map[string]requestInvocationEntity `yaml:"members"`
}

type requestInvocationBinding struct {
	Name  string `yaml:"name"`
	Field string `yaml:"field"`
}

type requestInvocationBindings struct {
	Path     []requestInvocationBinding `yaml:"path"`
	Query    []requestInvocationBinding `yaml:"query"`
	Header   []requestInvocationBinding `yaml:"header"`
	Injected []requestInvocationBinding `yaml:"injected"`
}

type serviceOperationEntityDocument struct {
	Operation        string                    `yaml:"operation"`
	ResponseEntity   string                    `yaml:"response_entity"`
	RequestEntity    string                    `yaml:"request_entity"`
	RequestBodyKind  string                    `yaml:"request_body_kind"`
	RequestBindings  requestInvocationBindings `yaml:"request_bindings"`
	ResponseBody     string                    `yaml:"response_body"`
	ResponseBodyKind string                    `yaml:"response_body_kind"`
}

func (v *validator) validateServiceEntities(
	dir,
	dirName,
	rootName string,
	fieldsEntities map[string]bool,
) {
	data, ok := v.readYAMLFile(filepath.Join(dir, "operations.yaml"))
	if !ok {
		return
	}
	// operations.yaml 使用顶层扁平 api_routes；这里只校验对象内可反向定位的响应契约。
	var parsed struct {
		APIRoutes []serviceOperationEntityDocument `yaml:"api_routes"`
	}
	if err := yaml.Unmarshal(data, &parsed); err != nil {
		return
	}
	var requestFields requestInvocationFieldsDocument
	fieldsData, fieldsOK := v.readYAMLFile(filepath.Join(dir, "fields.yaml"))
	if fieldsOK {
		if err := yaml.Unmarshal(fieldsData, &requestFields); err != nil {
			v.errorf("%s/fields.yaml: parse error: %v", dirName, err)
			fieldsOK = false
		}
	}

	for _, op := range parsed.APIRoutes {
		opName := strings.TrimSpace(op.Operation)
		requestKind := strings.TrimSpace(op.RequestBodyKind)
		if requestKind != "" && !requestBodyKinds[requestKind] {
			v.errorf("%s/operations.yaml: operation %q has invalid request_body_kind %q (allowed: object|none)",
				dirName, opName, requestKind)
		} else if requestKind != "" {
			if !fieldsOK {
				v.errorf(
					"%s/operations.yaml: operation %q cannot validate request_entity without fields.yaml",
					dirName,
					opName,
				)
			} else {
				for _, issue := range validateInvocationRequestShape(
					op,
					rootName,
					requestFields,
				) {
					v.errorf("%s/operations.yaml: %s", dirName, issue)
				}
			}
		}
		// response_entity 既可指向 fields.yaml entity，也可指向 projection read_model（如各类 *View/*Summary）。
		if op.ResponseEntity != "" && !fieldsEntities[op.ResponseEntity] && !v.fieldEntities[op.ResponseEntity] && !v.projectionReadModels[op.ResponseEntity] {
			v.warnf("%s/operations.yaml: operation %q references response_entity %q not in fields.yaml nor any projection read_model",
				dirName, opName, op.ResponseEntity)
		}

		body := strings.TrimSpace(op.ResponseBody)
		responseEntity := strings.TrimSpace(op.ResponseEntity)
		kind := strings.TrimSpace(op.ResponseBodyKind)
		// response_entity 是精确响应 wire 的唯一真相源。response_body 仅为尚未
		// 迁移对象的旧 OpenAPI item hint，不得覆盖或否定 canonical entity。
		if responseEntity == "" && body == "" && kind == "" {
			continue
		}
		if kind == "" && body != "" {
			v.errorf("%s/operations.yaml: operation %q declares response_body %q but missing response_body_kind (object|page|ack|upgrade)",
				dirName, opName, body)
			continue
		}
		if kind != "" && !responseBodyKinds[kind] {
			v.errorf("%s/operations.yaml: operation %q has invalid response_body_kind %q (allowed: object|page|ack|upgrade)",
				dirName, opName, kind)
			continue
		}
		if kind == "ack" || kind == "upgrade" {
			if body != "" {
				v.errorf("%s/operations.yaml: operation %q response_body_kind=%s must not declare response_body (got %q)",
					dirName, opName, kind, body)
			}
			continue
		}
		// object | page 优先使用 response_entity；仅旧对象回退 response_body。
		resolvedResponse := responseEntity
		if resolvedResponse == "" {
			resolvedResponse = body
		}
		if resolvedResponse == "" {
			v.errorf("%s/operations.yaml: operation %q response_body_kind=%s requires a response_body read model reference",
				dirName, opName, kind)
			continue
		}
		if !fieldsEntities[resolvedResponse] &&
			!v.fieldEntities[resolvedResponse] &&
			!v.projectionReadModels[resolvedResponse] {
			v.errorf("%s/operations.yaml: operation %q canonical response %q is not a known fields entity or projection read_model",
				dirName, opName, resolvedResponse)
		}
	}
}

func validateInvocationRequestShape(
	operation serviceOperationEntityDocument,
	rootName string,
	fields requestInvocationFieldsDocument,
) []string {
	operationName := strings.TrimSpace(operation.Operation)
	requestEntity := strings.TrimSpace(operation.RequestEntity)
	requestKind := strings.TrimSpace(operation.RequestBodyKind)
	if requestEntity == "" {
		return []string{fmt.Sprintf(
			"operation %q request_body_kind=%s requires request_entity",
			operationName,
			requestKind,
		)}
	}
	entity, err := findInvocationRequestEntity(fields, rootName, requestEntity)
	if err != nil {
		return []string{fmt.Sprintf("operation %q: %v", operationName, err)}
	}

	var issues []string
	entityFields := make(map[string]struct{}, len(entity.Fields))
	for _, field := range entity.Fields {
		name := strings.TrimSpace(field.Name)
		if name == "" {
			issues = append(issues, fmt.Sprintf(
				"operation %q request_entity %q has an empty field",
				operationName,
				requestEntity,
			))
			continue
		}
		if _, exists := entityFields[name]; exists {
			issues = append(issues, fmt.Sprintf(
				"operation %q request_entity %q repeats field %q",
				operationName,
				requestEntity,
				name,
			))
			continue
		}
		entityFields[name] = struct{}{}
	}

	boundFields := make(map[string]string)
	for _, group := range []struct {
		name   string
		values []requestInvocationBinding
	}{
		{name: "path", values: operation.RequestBindings.Path},
		{name: "query", values: operation.RequestBindings.Query},
		{name: "header", values: operation.RequestBindings.Header},
		{name: "injected", values: operation.RequestBindings.Injected},
	} {
		for _, binding := range group.values {
			field := strings.TrimSpace(binding.Field)
			if field == "" {
				issues = append(issues, fmt.Sprintf(
					"operation %q request_bindings.%s has an empty field",
					operationName,
					group.name,
				))
				continue
			}
			if _, exists := entityFields[field]; !exists {
				issues = append(issues, fmt.Sprintf(
					"operation %q request_bindings.%s field %q is absent from request_entity %q",
					operationName,
					group.name,
					field,
					requestEntity,
				))
			}
			if previous, exists := boundFields[field]; exists {
				issues = append(issues, fmt.Sprintf(
					"operation %q request field %q is bound to both %s and %s",
					operationName,
					field,
					previous,
					group.name,
				))
				continue
			}
			boundFields[field] = group.name
		}
	}

	var unboundFields []string
	for field := range entityFields {
		if _, bound := boundFields[field]; !bound {
			unboundFields = append(unboundFields, field)
		}
	}
	sort.Strings(unboundFields)
	switch requestKind {
	case "none":
		if len(unboundFields) > 0 {
			issues = append(issues, fmt.Sprintf(
				"operation %q request_body_kind=none leaves request_entity %q fields without canonical non-body bindings: %s",
				operationName,
				requestEntity,
				strings.Join(unboundFields, ", "),
			))
		}
	case "object":
		if len(unboundFields) == 0 {
			issues = append(issues, fmt.Sprintf(
				"operation %q request_body_kind=object has no body fields after canonical non-body bindings",
				operationName,
			))
		}
	}
	return issues
}

func findInvocationRequestEntity(
	fields requestInvocationFieldsDocument,
	rootName,
	requestEntity string,
) (requestInvocationEntity, error) {
	var matches []requestInvocationEntity
	for _, catalog := range []map[string]requestInvocationEntity{
		fields.Entities,
		fields.Types,
		fields.ValueObjects,
		fields.Members,
	} {
		if entity, exists := catalog[requestEntity]; exists {
			matches = append(matches, entity)
		}
	}
	if strings.TrimSpace(fields.Entity) == requestEntity ||
		(strings.TrimSpace(fields.Entity) == "" && strings.TrimSpace(rootName) == requestEntity) {
		matches = append(matches, requestInvocationEntity{Fields: fields.Fields})
	}
	if len(matches) == 0 {
		return requestInvocationEntity{}, fmt.Errorf(
			"request_entity %q is absent from fields.yaml",
			requestEntity,
		)
	}
	if len(matches) > 1 {
		return requestInvocationEntity{}, fmt.Errorf(
			"request_entity %q is declared more than once in fields.yaml",
			requestEntity,
		)
	}
	return matches[0], nil
}
