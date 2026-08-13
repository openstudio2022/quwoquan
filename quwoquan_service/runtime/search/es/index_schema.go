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
	// analyzerIndex tokenizes Chinese via IK semantic segmentation (ik_max_word:
	// fine-grained index-side splits). The Elasticsearch distribution is pinned
	// to quwoquan/elasticsearch-cjk which bundles analysis-ik + analysis-pinyin;
	// OpenSearch portability was explicitly given up
	// (specs/feature-tree/global-search-experience/design.md#dec-002).
	analyzerIndex = "qwq_cjk"
	// analyzerSearch uses coarse-grained ik_smart at query time and additionally
	// applies the synonym graph when configured.
	analyzerSearch = "qwq_cjk_search"
	// analyzerPinyin indexes short name/title fields as full pinyin + joined
	// pinyin + first-letter initials so Chinese objects match latin-input
	// queries ("dali"/"dl" -> 大理). Never applied to summary/body: pinyin
	// expansion on long text inflates the index without recall value.
	analyzerPinyin = "qwq_pinyin"
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
	filters := map[string]any{}
	// ik_max_word keeps recall high on the index side; ik_smart keeps query-side
	// terms coarse so multi_match does not over-fragment the user query.
	// lowercase normalizes embedded latin terms (IK leaves case untouched).
	indexFilter := []any{"lowercase"}
	searchFilter := []any{"lowercase"}
	if len(c.Synonyms) > 0 {
		filters["qwq_synonym"] = map[string]any{
			"type":     "synonym_graph",
			"synonyms": toAnySlice(c.Synonyms),
			"lenient":  true,
		}
		searchFilter = append(searchFilter, "qwq_synonym")
	}
	tokenizers := map[string]any{
		// pinyin tokenizer: per-hanzi full pinyin plus the joined full string and
		// the whole-field first-letter token. Latin input is segmented into
		// pinyin syllables on BOTH sides (none_chinese_pinyin_tokenize), so a
		// "dali" query becomes da+li and matches 大理's indexed tokens. Bare
		// initials ("dl") only match via the joined first-letter token and are
		// deliberately a suggest-index concern, not a result recall promise.
		"qwq_pinyin_tokenizer": map[string]any{
			"type":                         "pinyin",
			"keep_full_pinyin":             true,
			"keep_joined_full_pinyin":      true,
			"keep_first_letter":            true,
			"keep_original":                false,
			"limit_first_letter_length":    16,
			"lowercase":                    true,
			"remove_duplicated_term":       true,
			"none_chinese_pinyin_tokenize": true,
		},
	}
	return map[string]any{
		"number_of_shards":   c.shards(),
		"number_of_replicas": c.replicas(),
		"analysis": map[string]any{
			"filter":    filters,
			"tokenizer": tokenizers,
			"analyzer": map[string]any{
				analyzerIndex: map[string]any{
					"type":      "custom",
					"tokenizer": "ik_max_word",
					"filter":    indexFilter,
				},
				analyzerSearch: map[string]any{
					"type":      "custom",
					"tokenizer": "ik_smart",
					"filter":    searchFilter,
				},
				analyzerPinyin: map[string]any{
					"type":      "custom",
					"tokenizer": "qwq_pinyin_tokenizer",
					"filter":    []any{"lowercase"},
				},
			},
		},
	}
}

func buildIndexMappings(c IndexSchemaConfig) map[string]any {
	props := map[string]any{
		"target":      keywordField(),
		"objectType":  keywordField(),
		"objectId":    keywordField(),
		"contentType": keywordField(),
		// Short name/title fields carry a .py pinyin sub-field for latin-input
		// recall. summary/body deliberately do not: pinyin (like edge_ngram)
		// inflates long-text indexes far beyond its recall value.
		"title":             textFieldWithKeywordAndPinyin(),
		"summary":           textField(),
		"body":              textField(),
		"tags":              keywordField(),
		"entities":          keywordField(),
		"authorId":          keywordField(),
		"authorName":        textFieldWithKeywordAndPinyin(),
		"authorDisplayName": textField(),
		"groupId":           keywordField(),
		"groupName":         textFieldWithKeywordAndPinyin(),
		"entityId":          keywordField(),
		"entityName":        textFieldWithKeywordAndPinyin(),
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
		"placeName": textFieldWithKeywordAndPinyin(),
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

func textFieldWithKeywordAndPinyin() map[string]any {
	f := textField()
	f["fields"] = map[string]any{
		"kw": map[string]any{"type": "keyword", "ignore_above": 256},
		"py": map[string]any{
			"type":     "text",
			"analyzer": analyzerPinyin,
		},
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
