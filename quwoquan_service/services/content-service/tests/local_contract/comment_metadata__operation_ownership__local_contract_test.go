package local_contract

import (
	"os"
	"path/filepath"
	"testing"

	"gopkg.in/yaml.v3"
)

type commentMetadataService struct {
	APIRoutes []commentMetadataOperation `yaml:"api_routes"`
}

type commentMetadataOperation struct {
	Operation     string `yaml:"operation"`
	Authorization struct {
		Principal       string `yaml:"principal"`
		OwnershipPolicy string `yaml:"ownership_policy"`
	} `yaml:"authorization"`
	Application struct {
		Kind           string `yaml:"kind"`
		AggregateOwner string `yaml:"aggregate_owner"`
		Reader         string `yaml:"reader"`
		Slice          string `yaml:"slice"`
	} `yaml:"application"`
	Commercial struct {
		Status      string `yaml:"status"`
		BlockReason string `yaml:"block_reason"`
		GapID       string `yaml:"gap_id"`
		TargetStory string `yaml:"target_story"`
	} `yaml:"commercial"`
	Reliability struct {
		TimeoutMS    int    `yaml:"timeout_ms"`
		Cancellation string `yaml:"cancellation"`
		RetryMode    string `yaml:"retry_mode"`
		MaxAttempts  int    `yaml:"max_attempts"`
		Idempotency  string `yaml:"idempotency"`
	} `yaml:"reliability"`
	ErrorCodes       []string `yaml:"error_codes"`
	ResponseBody     string   `yaml:"response_body"`
	ResponseBodyKind string   `yaml:"response_body_kind"`
}

func TestCommentMetadataOwnsAllCanonicalOperationsWithReadyTransport(t *testing.T) {
	metadataRoot := filepath.Clean("../../../../contracts/metadata/content/comment")
	for _, name := range []string{
		"entity.yaml",
		"fields.yaml",
		"service.yaml",
		"errors.yaml",
		"events.yaml",
		"storage.yaml",
	} {
		if _, err := os.Stat(filepath.Join(metadataRoot, name)); err != nil {
			t.Fatalf("Comment metadata must include %s: %v", name, err)
		}
	}

	raw, err := os.ReadFile(filepath.Join(metadataRoot, "service.yaml"))
	if err != nil {
		t.Fatal(err)
	}
	var service commentMetadataService
	if err := yaml.Unmarshal(raw, &service); err != nil {
		t.Fatalf("decode comment service metadata: %v", err)
	}
	operations := make(map[string]commentMetadataOperation, len(service.APIRoutes))
	for _, operation := range service.APIRoutes {
		operations[operation.Operation] = operation
	}
	expectedKinds := map[string]string{
		"CreateComment":             "command",
		"DeleteComment":             "command",
		"PinComment":                "command",
		"UnpinComment":              "command",
		"BindMediaAssetsToComment":  "command",
		"ListComments":              "query",
		"ListCommentReplies":        "query",
		"ListCommentsByAuthor":      "query",
		"ListCommentsForPostAuthor": "query",
	}
	expectedQueryBodies := map[string]string{
		"ListComments":              "CommentPageSlice",
		"ListCommentReplies":        "ReplyPageSlice",
		"ListCommentsByAuthor":      "AuthorCommentPageSlice",
		"ListCommentsForPostAuthor": "ReceivedCommentPageSlice",
	}
	for name, expectedKind := range expectedKinds {
		operation, found := operations[name]
		if !found {
			t.Errorf("canonical Comment operation %s is missing", name)
			continue
		}
		if operation.Application.Kind != expectedKind {
			t.Errorf("%s kind = %q, want %q", name, operation.Application.Kind, expectedKind)
		}
		if operation.Authorization.Principal == "" || operation.Authorization.OwnershipPolicy == "" {
			t.Errorf("%s must declare principal and ownership policy", name)
		}
		if operation.Reliability.TimeoutMS <= 0 ||
			operation.Reliability.Cancellation == "" ||
			operation.Reliability.RetryMode == "" ||
			operation.Reliability.MaxAttempts <= 0 ||
			operation.Reliability.Idempotency == "" {
			t.Errorf("%s must declare complete reliability policy", name)
		}
		if len(operation.ErrorCodes) == 0 {
			t.Errorf("%s must declare error codes", name)
		}
		if operation.Commercial.Status != "ready" ||
			operation.Commercial.BlockReason != "" ||
			operation.Commercial.GapID != "" ||
			operation.Commercial.TargetStory != "" {
			t.Errorf("%s must declare ready transport composition: %+v", name, operation.Commercial)
		}
		if expectedKind == "command" && operation.Application.AggregateOwner != "Comment" {
			t.Errorf("%s aggregate owner = %q, want Comment", name, operation.Application.AggregateOwner)
		}
		if expectedKind == "query" &&
			(operation.Application.Reader == "" || operation.Application.Slice == "") {
			t.Errorf("%s must bind named reader and typed slice", name)
		}
		if expectedBody, isQuery := expectedQueryBodies[name]; isQuery {
			expectedKind := "page"
			if operation.Application.Slice != expectedBody ||
				operation.ResponseBody != expectedBody ||
				operation.ResponseBodyKind != expectedKind {
				t.Errorf(
					"%s response metadata drift: slice=%q body=%q kind=%q",
					name,
					operation.Application.Slice,
					operation.ResponseBody,
					operation.ResponseBodyKind,
				)
			}
		}
	}
}

func TestCommentMetadataDeclaresTransactionalOutboxAndNamedReadModels(t *testing.T) {
	metadataRoot := filepath.Clean("../../../../contracts/metadata/content/comment")
	var storage struct {
		Collections map[string]struct{} `yaml:"collections"`
		Transaction struct {
			Scope      []string `yaml:"scope"`
			Guarantees []string `yaml:"guarantees"`
		} `yaml:"transaction"`
	}
	raw, err := os.ReadFile(filepath.Join(metadataRoot, "storage.yaml"))
	if err != nil {
		t.Fatalf("read Comment storage metadata: %v", err)
	}
	if err := yaml.Unmarshal(raw, &storage); err != nil {
		t.Fatalf("decode Comment storage metadata: %v", err)
	}
	for _, collection := range []string{
		"comments",
		"comment_command_receipts",
		"comment_outbox",
	} {
		if _, found := storage.Collections[collection]; !found {
			t.Errorf("Comment storage misses %s", collection)
		}
		if !containsCommentMetadataValue(storage.Transaction.Scope, collection) {
			t.Errorf("Comment transaction scope misses %s", collection)
		}
	}
	for _, guarantee := range []string{
		"version_cas",
		"idempotency_digest",
		"aggregate_and_outbox_atomic_commit",
	} {
		if !containsCommentMetadataValue(storage.Transaction.Guarantees, guarantee) {
			t.Errorf("Comment transaction misses guarantee %s", guarantee)
		}
	}

	expectedProjections := map[string]string{
		"comment_page_slice.yaml":          "CommentPageSlice",
		"reply_page_slice.yaml":            "ReplyPageSlice",
		"author_comment_page_slice.yaml":   "AuthorCommentPageSlice",
		"received_comment_page_slice.yaml": "ReceivedCommentPageSlice",
	}
	for fileName, expectedReadModel := range expectedProjections {
		raw, err := os.ReadFile(filepath.Join(metadataRoot, "projections", fileName))
		if err != nil {
			t.Errorf("read Comment projection %s: %v", fileName, err)
			continue
		}
		var projection struct {
			ReadModel string `yaml:"read_model"`
		}
		if err := yaml.Unmarshal(raw, &projection); err != nil {
			t.Errorf("decode Comment projection %s: %v", fileName, err)
			continue
		}
		if projection.ReadModel != expectedReadModel {
			t.Errorf("%s read model = %q, want %q", fileName, projection.ReadModel, expectedReadModel)
		}
	}

	raw, err = os.ReadFile(filepath.Join(metadataRoot, "events.yaml"))
	if err != nil {
		t.Fatalf("read Comment events metadata: %v", err)
	}
	var events struct {
		Events []struct {
			Name    string `yaml:"name"`
			Channel string `yaml:"channel"`
		} `yaml:"events"`
	}
	if err := yaml.Unmarshal(raw, &events); err != nil {
		t.Fatalf("decode Comment events metadata: %v", err)
	}
	eventChannels := make(map[string]string, len(events.Events))
	for _, event := range events.Events {
		eventChannels[event.Name] = event.Channel
	}
	for _, eventName := range []string{
		"CommentCreated",
		"CommentDeleted",
		"CommentPinChanged",
		"CommentAttachmentsBound",
	} {
		if eventChannels[eventName] != "outbox" {
			t.Errorf("%s must be emitted through the Comment outbox", eventName)
		}
	}
}

func containsCommentMetadataValue(values []string, want string) bool {
	for _, value := range values {
		if value == want {
			return true
		}
	}
	return false
}
