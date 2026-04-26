package failures

import "strings"

type Context struct {
	Attributes []ContextAttribute `json:"attributes"`
}

type ContextAttribute struct {
	Key   string `json:"key"`
	Value string `json:"value"`
}

func (c Context) Normalized() Context {
	attributes := make([]ContextAttribute, 0, len(c.Attributes))
	for _, attribute := range c.Attributes {
		normalized := attribute.Normalized()
		if normalized.Key == "" {
			continue
		}
		attributes = append(attributes, normalized)
	}
	c.Attributes = attributes
	return c
}

func (a ContextAttribute) Normalized() ContextAttribute {
	a.Key = strings.TrimSpace(a.Key)
	a.Value = strings.TrimSpace(a.Value)
	return a
}
