// Command search-index-schema emits the canonical Elasticsearch create-index
// body owned by runtime/search/es. Local migration tooling consumes this
// command instead of duplicating analyzer or mapping definitions.
package main

import (
	"encoding/json"
	"flag"
	"log"
	"os"

	"quwoquan_service/runtime/search/es"
)

func main() {
	shards := flag.Int("shards", 0, "number_of_shards (0 = canonical default)")
	replicas := flag.Int("replicas", 0, "number_of_replicas (0 = canonical default)")
	embeddingDims := flag.Int("embedding-dims", 0, "dense-vector dimensions (0 = disabled)")
	flag.Parse()

	body := es.BuildCreateIndexBody(es.IndexSchemaConfig{
		NumberOfShards:   *shards,
		NumberOfReplicas: *replicas,
		EmbeddingDims:    *embeddingDims,
	})
	encoder := json.NewEncoder(os.Stdout)
	encoder.SetEscapeHTML(false)
	if err := encoder.Encode(body); err != nil {
		log.Fatalf("encode canonical search index schema: %v", err)
	}
}
