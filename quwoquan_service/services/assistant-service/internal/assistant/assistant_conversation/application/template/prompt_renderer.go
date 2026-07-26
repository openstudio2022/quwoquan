package template

import (
	"fmt"
	"regexp"
)

var variablePattern = regexp.MustCompile(`\{\{\s*([a-zA-Z0-9_.-]+)\s*\}\}`)

type Catalog struct {
	Templates map[string]string
}

func NewCatalog(templates map[string]string) Catalog {
	return Catalog{Templates: mapsClone(templates)}
}

func (c Catalog) Resolve(templateID string) (string, bool) {
	if c.Templates == nil {
		return "", false
	}
	value, ok := c.Templates[templateID]
	return value, ok
}

type PromptRenderer struct {
	Catalog Catalog
}

func (r PromptRenderer) Render(templateID string, values map[string]string) (string, error) {
	raw, ok := r.Catalog.Resolve(templateID)
	if !ok {
		return "", fmt.Errorf("prompt template %q not found", templateID)
	}
	return variablePattern.ReplaceAllStringFunc(raw, func(token string) string {
		matches := variablePattern.FindStringSubmatch(token)
		if len(matches) != 2 {
			return token
		}
		if value, ok := values[matches[1]]; ok {
			return value
		}
		return ""
	}), nil
}

func mapsClone(in map[string]string) map[string]string {
	if in == nil {
		return nil
	}
	out := make(map[string]string, len(in))
	for key, value := range in {
		out[key] = value
	}
	return out
}
