package es

// IndexSchemaConfig controls how the unified object index is created (settings +
// mappings). It is supplied by the service from its package effective config,
// rendered from config/schema.yaml plus environments/<env>/config.yaml, so the
// analyzer chain, sharding and synonyms are auditable and environment-specific.
type IndexSchemaConfig struct {
	// NumberOfShards / NumberOfReplicas default to 1 when unset.
	NumberOfShards   int
	NumberOfReplicas int
	// Synonyms are ES synonym_graph rules (e.g. "民宿,客栈" or "番茄 => 西红柿").
	// When empty the synonym filter is omitted from the search analyzer.
	Synonyms []string
	// EmbeddingDims > 0 enables the dense_vector field used by hybrid kNN/RRF.
	EmbeddingDims int
}

const (
	// analyzerIndex tokenizes Chinese via CJK bigrams (no external plugin needed),
	// so the index is portable across self-hosted ES and OpenSearch.
	analyzerIndex = "qwq_cjk"
	// analyzerSearch additionally applies the synonym graph at query time.
	analyzerSearch = "qwq_cjk_search"
)

func (c IndexSchemaConfig) shards() int {
	if c.NumberOfShards > 0 {
		return c.NumberOfShards
	}
	return 1
}

func (c IndexSchemaConfig) replicas() int {
	if c.NumberOfReplicas > 0 {
		return c.NumberOfReplicas
	}
	return 1
}

// BuildCreateIndexBody returns the PUT /{index} request body (settings+mappings).
func BuildCreateIndexBody(c IndexSchemaConfig) map[string]any {
	return map[string]any{
		"settings": buildIndexSettings(c),
		"mappings": buildIndexMappings(c),
	}
}

func buildIndexSettings(c IndexSchemaConfig) map[string]any {
	filters := map[string]any{
		"qwq_cjk_bigram": map[string]any{
			"type":            "cjk_bigram",
			"output_unigrams": true,
		},
	}
	indexFilter := []any{"cjk_width", "lowercase", "qwq_cjk_bigram"}
	searchFilter := []any{"cjk_width", "lowercase", "qwq_cjk_bigram"}
	if len(c.Synonyms) > 0 {
		filters["qwq_synonym"] = map[string]any{
			"type":     "synonym_graph",
			"synonyms": toAnySlice(c.Synonyms),
			"lenient":  true,
		}
		searchFilter = append(searchFilter, "qwq_synonym")
	}
	return map[string]any{
		"number_of_shards":   c.shards(),
		"number_of_replicas": c.replicas(),
		"analysis": map[string]any{
			"filter": filters,
			"analyzer": map[string]any{
				analyzerIndex: map[string]any{
					"type":      "custom",
					"tokenizer": "standard",
					"filter":    indexFilter,
				},
				analyzerSearch: map[string]any{
					"type":      "custom",
					"tokenizer": "standard",
					"filter":    searchFilter,
				},
			},
		},
	}
}

func buildIndexMappings(c IndexSchemaConfig) map[string]any {
	props := map[string]any{
		"target":            keywordField(),
		"objectType":        keywordField(),
		"objectId":          keywordField(),
		"contentType":       keywordField(),
		"title":             textFieldWithKeyword(),
		"summary":           textField(),
		"body":              textField(),
		"tags":              keywordField(),
		"entities":          keywordField(),
		"authorId":          keywordField(),
		"authorName":        textFieldWithKeyword(),
		"authorDisplayName": textField(),
		"groupId":           keywordField(),
		"groupName":         textFieldWithKeyword(),
		"entityId":          keywordField(),
		"entityName":        textFieldWithKeyword(),
		"conversationId":    keywordField(),
		"visibility":        keywordField(),
		"quality":           map[string]any{"type": "float"},
		"updatedAt":         map[string]any{"type": "date"},
		// Object-specific public presentation fields are retained in _source but
		// never dynamically indexed. Search/filter truth remains in the explicit
		// fields above.
		"payload": map[string]any{"type": "object", "enabled": false},
		// Cross-object location dimension (R-S05e): geo enables geo_distance
		// ("附近") recall + distance sort; placeId/placeName carry the place
		// reference. All optional — only objects with a real location populate them.
		"geo":       map[string]any{"type": "geo_point"},
		"placeId":   keywordField(),
		"placeName": textFieldWithKeyword(),
	}
	if c.EmbeddingDims > 0 {
		props["embedding"] = map[string]any{
			"type":       "dense_vector",
			"dims":       c.EmbeddingDims,
			"index":      true,
			"similarity": "cosine",
		}
	}
	return map[string]any{"properties": props}
}

func textField() map[string]any {
	return map[string]any{
		"type":            "text",
		"analyzer":        analyzerIndex,
		"search_analyzer": analyzerSearch,
	}
}

func textFieldWithKeyword() map[string]any {
	f := textField()
	f["fields"] = map[string]any{
		"kw": map[string]any{"type": "keyword", "ignore_above": 256},
	}
	return f
}

func keywordField() map[string]any {
	return map[string]any{"type": "keyword"}
}

func toAnySlice(values []string) []any {
	out := make([]any, 0, len(values))
	for _, v := range values {
		out = append(out, v)
	}
	return out
}
