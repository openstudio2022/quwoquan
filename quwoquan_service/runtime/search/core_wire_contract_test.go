package search

import (
	"encoding/json"
	"testing"
	"time"
)

func TestRetrieveWireValueObjectsUseLowerCamelCaseKeys(t *testing.T) {
	generatedAt := time.Date(2026, time.July, 20, 10, 0, 0, 0, time.UTC)
	fixtures := []struct {
		name      string
		value     any
		wantKeys  []string
		forbidden []string
	}{
		{
			name: "citation",
			value: Citation{
				CitationID: "citation-1", ObjectType: "content.post",
				ObjectID: "post-1", Title: "标题", SourceDomain: "content",
				Score: 0.9,
			},
			wantKeys:  []string{"citationId", "objectType", "objectId", "title", "sourceDomain", "score"},
			forbidden: []string{"CitationID", "ObjectType", "ObjectID", "Title", "SourceDomain", "Score"},
		},
		{
			name:      "reason",
			value:     Reason{Code: "semantic_match", Label: "语义相关", Weight: 0.8},
			wantKeys:  []string{"code", "label", "weight"},
			forbidden: []string{"Code", "Label", "Weight"},
		},
		{
			name:      "evidence",
			value:     Evidence{Field: "title", Snippet: "摄影"},
			wantKeys:  []string{"field", "snippet"},
			forbidden: []string{"Field", "Snippet"},
		},
		{
			name:      "facet",
			value:     Facet{Key: "article", Label: "长文", Count: 2},
			wantKeys:  []string{"key", "label", "count"},
			forbidden: []string{"Key", "Label", "Count"},
		},
		{
			name:      "degrade signal",
			value:     DegradeSignal{Code: "partial", Message: "部分结果不可用", ObjectType: "content.post"},
			wantKeys:  []string{"code", "message", "objectType"},
			forbidden: []string{"Code", "Message", "ObjectType"},
		},
		{
			name:      "provenance",
			value:     Provenance{Provider: "elasticsearch", IndexVersion: "search-v1", GeneratedAt: generatedAt},
			wantKeys:  []string{"provider", "indexVersion", "generatedAt"},
			forbidden: []string{"Provider", "IndexVersion", "GeneratedAt"},
		},
	}

	for _, fixture := range fixtures {
		t.Run(fixture.name, func(t *testing.T) {
			raw, err := json.Marshal(fixture.value)
			if err != nil {
				t.Fatalf("marshal %s: %v", fixture.name, err)
			}
			var object map[string]any
			if err := json.Unmarshal(raw, &object); err != nil {
				t.Fatalf("decode %s: %v", fixture.name, err)
			}
			for _, key := range fixture.wantKeys {
				if _, ok := object[key]; !ok {
					t.Errorf("missing lowerCamelCase key %q in %s", key, raw)
				}
			}
			for _, key := range fixture.forbidden {
				if _, ok := object[key]; ok {
					t.Errorf("exported Go field leaked as key %q in %s", key, raw)
				}
			}
		})
	}
}
