package presentation

import (
	"fmt"
	"strings"

	generated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
)

type Catalog struct {
	byRef map[string]Template
}

func NewCatalog(templates []Template) (*Catalog, error) {
	catalog := &Catalog{byRef: make(map[string]Template, len(templates))}
	for _, template := range templates {
		if err := ValidateTemplate(template); err != nil {
			return nil, err
		}
		ref := TemplateRef(template)
		if _, exists := catalog.byRef[ref]; exists {
			return nil, fmt.Errorf("duplicate presentation template %q", ref)
		}
		catalog.byRef[ref] = cloneTemplate(template)
	}
	return catalog, nil
}

func (c *Catalog) Resolve(ref, skillID string) (Template, error) {
	if c == nil {
		return Template{}, ErrTemplateUnavailable
	}
	template, ok := c.byRef[strings.TrimSpace(ref)]
	if !ok || template.SkillID != strings.TrimSpace(skillID) {
		return Template{}, ErrTemplateUnavailable
	}
	return cloneTemplate(template), nil
}

func TemplateRef(template Template) string {
	return strings.TrimSpace(template.TemplateID) + "@" + strings.TrimSpace(template.AssetDigest)
}

func cloneTemplate(value Template) Template {
	value.InputSchema = cloneMap(value.InputSchema)
	value.Nodes = cloneNodes(value.Nodes)
	value.ResponsiveVariants = append([]ResponsiveVariant{}, value.ResponsiveVariants...)
	for index := range value.ResponsiveVariants {
		value.ResponsiveVariants[index].RequiredNodeKinds = append(
			[]generated.AssistantPresentationNodeKind{},
			value.ResponsiveVariants[index].RequiredNodeKinds...,
		)
	}
	value.AllowedActionIntents = append([]string{}, value.AllowedActionIntents...)
	value.Accessibility = cloneMap(value.Accessibility)
	return value
}
