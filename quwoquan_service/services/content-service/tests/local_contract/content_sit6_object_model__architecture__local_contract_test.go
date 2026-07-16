package local_contract

import (
	"os"
	"path/filepath"
	"testing"

	"gopkg.in/yaml.v3"
)

type sit6EntityDocument struct {
	Entity     string `yaml:"entity"`
	ObjectKind string `yaml:"object_kind"`
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
	metadataRoot := filepath.Clean("../../../../contracts/metadata/content")
	type expectedObject struct {
		name string
		kind string
	}
	required := map[string]expectedObject{
		"comment":                    {name: "Comment", kind: "aggregate_root"},
		"content_reaction":           {name: "ContentReaction", kind: "aggregate_root"},
		"outbound_share_fact":        {name: "OutboundShareFact", kind: "append_only_fact"},
		"media_upload_session":       {name: "MediaUploadSession", kind: "aggregate_root"},
		"media_asset":                {name: "MediaAsset", kind: "aggregate_root"},
		"media_original_access_fact": {name: "MediaOriginalAccessFact", kind: "append_only_fact"},
		"post_moderation_case":       {name: "PostModerationCase", kind: "aggregate_root"},
		"report":                     {name: "Report", kind: "aggregate_root"},
		"deleted_post_tombstone":     {name: "DeletedPostTombstone", kind: "append_only_fact"},
	}
	for dir, expected := range required {
		path := filepath.Join(metadataRoot, dir, "entity.yaml")
		raw, err := os.ReadFile(path)
		if err != nil {
			t.Fatalf("SIT6 object metadata missing %s: %v", path, err)
		}
		var document sit6EntityDocument
		if err := yaml.Unmarshal(raw, &document); err != nil {
			t.Fatalf("decode %s: %v", path, err)
		}
		if document.Entity != expected.name || document.ObjectKind != expected.kind {
			t.Fatalf(
				"%s must declare %s as %s, got entity=%q kind=%q",
				path,
				expected.name,
				expected.kind,
				document.Entity,
				document.ObjectKind,
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
	metadataRoot := filepath.Clean("../../../../contracts/metadata/content")
	servicePaths, err := filepath.Glob(filepath.Join(metadataRoot, "*", "service.yaml"))
	if err != nil {
		t.Fatal(err)
	}
	owners := make(map[string]string, len(expected))
	ownerSources := make(map[string]string, len(expected))
	for _, servicePath := range servicePaths {
		raw, err := os.ReadFile(servicePath)
		if err != nil {
			t.Fatal(err)
		}
		var document sit6ServiceDocument
		if err := yaml.Unmarshal(raw, &document); err != nil {
			t.Fatalf("decode %s: %v", servicePath, err)
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
					servicePath,
				)
				continue
			}
			owner := route.Application.AggregateOwner
			if owner == "" {
				owner = route.Application.AppendSink
			}
			owners[route.Operation] = owner
			ownerSources[route.Operation] = servicePath
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
