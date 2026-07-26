// spec_ref: specs/feature-tree/discovery-content/content-service-contract-foundation/spec.md#sit-001
package local_contract

import (
	"os"
	"path/filepath"
	"testing"

	"gopkg.in/yaml.v3"
)

type sit6ObjectDocument struct {
	Kind string `yaml:"kind"`
}

type sit6ServiceDocument struct {
	APIRoutes []struct {
		Operation   string `yaml:"operation"`
		Application struct {
			AggregateOwner string `yaml:"aggregate_owner"`
			AppendSink     string `yaml:"append_sink"`
		} `yaml:"application"`
	} `yaml:"api_routes"`
}

func TestContentSIT6IndependentLifecycleObjectsAreCanonical(t *testing.T) {
	type expectedObject struct {
		context string
		kind    string
	}
	required := map[string]expectedObject{
		"comment":                    {context: "content", kind: "aggregate_root"},
		"content_reaction":           {context: "content", kind: "aggregate_root"},
		"outbound_share_fact":        {context: "content", kind: "append_only_fact"},
		"media_upload_session":       {context: "media", kind: "aggregate_root"},
		"media_asset":                {context: "media", kind: "aggregate_root"},
		"media_original_access_fact": {context: "media", kind: "append_only_fact"},
		"post_moderation_case":       {context: "trust_safety", kind: "aggregate_root"},
		"report":                     {context: "trust_safety", kind: "aggregate_root"},
		"deleted_post_tombstone":     {context: "content", kind: "append_only_fact"},
	}
	for dir, expected := range required {
		path := filepath.Join(
			quwoquanServiceRoot(t),
			"services/content-service/contracts",
			expected.context,
			dir,
			"object.yaml",
		)
		raw, err := os.ReadFile(path)
		if err != nil {
			t.Fatalf("SIT6 object metadata missing %s: %v", path, err)
		}
		var document sit6ObjectDocument
		if err := yaml.Unmarshal(raw, &document); err != nil {
			t.Fatalf("decode %s: %v", path, err)
		}
		if document.Kind != expected.kind {
			t.Fatalf(
				"%s must declare kind %s, got %q",
				path,
				expected.kind,
				document.Kind,
			)
		}
	}
}

func TestContentSIT6CommandsBindToTheirAggregateOwners(t *testing.T) {
	expected := map[string]string{
		"CreateComment":              "Comment",
		"DeleteComment":              "Comment",
		"ReactToComment":             "ContentReaction",
		"LikePost":                   "ContentReaction",
		"UnlikePost":                 "ContentReaction",
		"CreateOutboundShare":        "OutboundShareFact",
		"InitMediaUpload":            "MediaUploadSession",
		"CompleteMediaUpload":        "MediaUploadSession",
		"AbortMediaUpload":           "MediaUploadSession",
		"RequestOriginalImageAccess": "MediaOriginalAccessFact",
		"SelectAutoVideoCover":       "MediaAsset",
		"SelectManualVideoCover":     "MediaAsset",
	}
	metadataRoot := filepath.Join(
		quwoquanServiceRoot(t),
		"services/content-service/contracts",
	)
	var operationPaths []string
	for _, context := range []string{"content", "media", "trust_safety"} {
		paths, err := filepath.Glob(filepath.Join(metadataRoot, context, "*", "operations.yaml"))
		if err != nil {
			t.Fatal(err)
		}
		operationPaths = append(operationPaths, paths...)
	}
	owners := make(map[string]string, len(expected))
	ownerSources := make(map[string]string, len(expected))
	for _, operationsPath := range operationPaths {
		raw, err := os.ReadFile(operationsPath)
		if err != nil {
			t.Fatal(err)
		}
		var document sit6ServiceDocument
		if err := yaml.Unmarshal(raw, &document); err != nil {
			t.Fatalf("decode %s: %v", operationsPath, err)
		}
		for _, route := range document.APIRoutes {
			if _, tracked := expected[route.Operation]; !tracked {
				continue
			}
			if previous, duplicate := ownerSources[route.Operation]; duplicate {
				t.Errorf(
					"%s owner is declared by multiple metadata sources: %s and %s",
					route.Operation,
					previous,
					operationsPath,
				)
				continue
			}
			owner := route.Application.AggregateOwner
			if owner == "" {
				owner = route.Application.AppendSink
			}
			owners[route.Operation] = owner
			ownerSources[route.Operation] = operationsPath
		}
	}
	for operation, aggregateOwner := range expected {
		if actual := owners[operation]; actual != aggregateOwner {
			t.Errorf(
				"%s aggregate owner = %q, want %q",
				operation,
				actual,
				aggregateOwner,
			)
		}
	}
}
