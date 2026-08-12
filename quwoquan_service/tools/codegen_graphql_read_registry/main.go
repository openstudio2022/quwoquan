package main

import (
	"flag"
	"fmt"
	"os"
	"strings"
)

func main() {
	var options Options
	var outputPath string
	var check bool
	flag.StringVar(&options.SchemaPath, "schema", "services/api-edge/resources/policies/graphql_read/schema.graphqls", "GraphQL SDL schema")
	flag.StringVar(&options.MetadataPath, "metadata", "services/api-edge/resources/policies/graphql_read/query_metadata.json", "manual query binding and policy metadata")
	flag.StringVar(&options.MetadataDir, "metadata-dir", "", "compiled service ContractGraph metadata view")
	flag.StringVar(&options.CandidateDigest, "candidate-digest", "", "immutable release candidate digest")
	flag.StringVar(&outputPath, "output", "services/api-edge/resources/policies/graphql_read/persisted_query_registry.example.json", "generated persisted query registry")
	flag.BoolVar(&check, "check", false, "fail unless output is byte-current")
	flag.Parse()

	options.SchemaPath = normalizedPath(options.SchemaPath)
	options.MetadataPath = normalizedPath(options.MetadataPath)
	options.MetadataDir = strings.TrimSpace(options.MetadataDir)
	if options.MetadataDir != "" {
		options.MetadataDir = normalizedPath(options.MetadataDir)
	}
	outputPath = normalizedPath(outputPath)
	encoded, err := Generate(options)
	if err == nil {
		err = WriteOrCheck(outputPath, encoded, check)
	}
	if err != nil {
		fmt.Fprintln(os.Stderr, "codegen_graphql_read_registry:", err)
		os.Exit(1)
	}
}
