package openapi

import (
	"fmt"
	"strings"
	"unicode"
)

type schemaRegistry struct {
	schemas map[string]openAPISchema
	origins map[string]string
}

func newSchemaRegistry(schemas map[string]openAPISchema) *schemaRegistry {
	return &schemaRegistry{
		schemas: schemas,
		origins: map[string]string{},
	}
}

func (registry *schemaRegistry) addPlaceholder(entity string) (string, error) {
	component := normalizeComponentName(entity)
	if err := registry.claim(component, "entity:"+entity); err != nil {
		return "", err
	}
	if _, exists := registry.schemas[component]; !exists {
		registry.schemas[component] = openAPISchema{
			Type:                 "object",
			Description:          "字段由 fields/projection codegen 契约定义；当前 OpenAPI compiler 仅保留命名引用。",
			XContractEntity:      entity,
			XContractPlaceholder: true,
		}
	}
	return component, nil
}

func (registry *schemaRegistry) addPage(
	name string,
	entity string,
	itemComponent string,
) (string, error) {
	component := normalizeComponentName(name)
	if err := registry.claim(component, "page:"+entity); err != nil {
		return "", err
	}
	if _, exists := registry.schemas[component]; !exists {
		registry.schemas[component] = openAPISchema{
			Type:            "object",
			Required:        []string{"items"},
			XContractEntity: entity,
			Properties: map[string]openAPISchema{
				"items": {
					Type: "array",
					Items: &openAPISchema{
						Ref: componentRef(itemComponent),
					},
				},
				"nextCursor": {
					Type:     "string",
					Nullable: true,
				},
			},
		}
	}
	return component, nil
}

func (registry *schemaRegistry) claim(component string, origin string) error {
	if component == "" {
		return fmt.Errorf("component name is empty")
	}
	if previous, exists := registry.origins[component]; exists && previous != origin {
		return fmt.Errorf(
			"component %q collides between %s and %s",
			component,
			previous,
			origin,
		)
	}
	registry.origins[component] = origin
	return nil
}

func normalizeComponentName(value string) string {
	var result strings.Builder
	for _, current := range strings.TrimSpace(value) {
		if unicode.IsLetter(current) || unicode.IsDigit(current) ||
			current == '.' || current == '_' || current == '-' {
			result.WriteRune(current)
		} else {
			result.WriteRune('_')
		}
	}
	normalized := result.String()
	if normalized == "" {
		return ""
	}
	first := rune(normalized[0])
	if unicode.IsDigit(first) {
		return "Schema_" + normalized
	}
	return normalized
}
