package main

const (
	searchAppClientGenerator  = "codegen_graphql_app_search_client"
	searchAppClientOutputPath = "lib/runtime/transport/graphql_read/generated/search_page.g.dart"
	searchAppManifestPath     = "tool/graphql_read_codegen/search_generated_manifest.json"
	searchPageOperationID     = "gateway.persisted_query_execution.SearchPage"
	searchPageOperationName   = "SearchPage"
	searchPageRootField       = "searchPage"
	searchPageInputType       = "SearchPageInput"
)

type searchGenerationInput struct {
	registry       registryDocument
	entry          registryEntry
	metadata       queryMetadataEntry
	responseKey    string
	inputType      string
	responseType   string
	selectedFields []string
	gateway        graphOperation
	operation      graphOperation
	appOperation   appLockOperation
	wireDocument   graphDocument
	registryDigest string
	graphDigest    string
	appLockDigest  string
	schemaDigest   string
}
