// spec_ref: specs/feature-tree/discovery-content/feed-orchestration-recommendation/streaming-feed-performance/spec.md#gwt-001
package recommendation

import (
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"gopkg.in/yaml.v3"
)

func TestRankedFeedWindowEntryBudgetsMatchCanonicalContentContract(t *testing.T) {
	var policy struct {
		TextLimits struct {
			TitleMaxRunes            int `yaml:"title_max_runes"`
			SemanticMentionsMaxItems int `yaml:"semantic_mentions_max_items"`
		} `yaml:"text_limits"`
	}
	policyPath := filepath.Join(
		"..", "..", "services", "content-service", "contracts", "content", "post", "publication_policy.yaml",
	)
	raw, err := os.ReadFile(policyPath)
	if err != nil {
		t.Fatalf("read canonical Post publication policy: %v", err)
	}
	if err := yaml.Unmarshal(raw, &policy); err != nil {
		t.Fatalf("decode canonical Post publication policy: %v", err)
	}
	if policy.TextLimits.TitleMaxRunes != rankedFeedWindowTitleMaxRunes ||
		policy.TextLimits.SemanticMentionsMaxItems != rankedFeedWindowMaxProjectedRefs {
		t.Fatalf("Ranked window entry budget drift: policy=%+v", policy.TextLimits)
	}

	fieldsPath := filepath.Join(
		"..", "..", "services", "content-service", "contracts", "content", "post", "fields.yaml",
	)
	fields := readCanonicalOwnerBudgetFields(t, fieldsPath)
	wantConstraints := map[string]string{
		"title":            "MAX_LENGTH_80",
		"semanticMentions": "MAX_ITEMS_30",
	}
	for _, field := range fields {
		want, tracked := wantConstraints[field.Name]
		if !tracked {
			continue
		}
		found := false
		for _, constraint := range field.Constraints {
			found = found || constraint == want
		}
		if !found {
			t.Fatalf("Post.%s no longer declares %s", field.Name, want)
		}
		delete(wantConstraints, field.Name)
	}
	if len(wantConstraints) != 0 {
		t.Fatalf("canonical Post fields missing budget owners: %v", wantConstraints)
	}
	if fields["_id"].Type != "ObjectId" {
		t.Fatalf("Post authoritative identity type drifted: %+v", fields["_id"])
	}
	discoveryFields := readCanonicalOwnerBudgetFields(
		t,
		filepath.Join(
			"..", "..", "services", "content-service", "contracts",
			"content", "post", "projections", "discovery_feed.yaml",
		),
	)
	assertCanonicalOwnerBudget(
		t,
		discoveryFields,
		"postId",
		rankedFeedWindowContentIDMaxBytes,
		0,
		0,
	)
	assertCanonicalOwnerBudget(
		t,
		fields,
		"authorId",
		rankedFeedWindowAuthorIDMaxBytes,
		0,
		0,
	)
	assertCanonicalOwnerBudget(
		t,
		fields,
		"title",
		rankedFeedWindowTitleMaxBytes,
		0,
		0,
	)
	assertCanonicalOwnerBudget(
		t,
		fields,
		"tagRefs",
		0,
		rankedFeedWindowMaxProjectedRefs,
		rankedFeedWindowTagRefMaxBytes,
	)
	assertCanonicalOwnerBudget(
		t,
		fields,
		"entityRefs",
		0,
		rankedFeedWindowMaxProjectedRefs,
		rankedFeedWindowEntityRefMaxBytes,
	)

	personaFields := readCanonicalOwnerBudgetFields(
		t,
		filepath.Join(
			"..", "..", "services", "user-service", "contracts",
			"persona_management", "persona", "fields.yaml",
		),
	)
	assertCanonicalOwnerBudget(
		t,
		personaFields,
		"personaId",
		rankedFeedWindowAuthorIDMaxBytes,
		0,
		0,
	)
	assertCanonicalOwnerBudget(t, personaFields, "displayName", 256, 0, 0)
	assertCanonicalOwnerBudget(t, personaFields, "avatarUrl", 4096, 0, 0)

	tagFields := readCanonicalOwnerBudgetFields(
		t,
		filepath.Join(
			"..", "..", "services", "tag-service", "contracts",
			"tag", "tag_node_view", "fields.yaml",
		),
	)
	assertCanonicalOwnerBudget(
		t,
		tagFields,
		"tagRef",
		rankedFeedWindowTagRefMaxBytes,
		0,
		0,
	)
	assertCanonicalOwnerBudget(t, tagFields, "label", 256, 0, 0)

	entityFields := readCanonicalOwnerBudgetFields(
		t,
		filepath.Join(
			"..", "..", "services", "entity-service", "contracts",
			"entity_homepage", "homepage", "fields.yaml",
		),
	)
	assertCanonicalOwnerBudget(
		t,
		entityFields,
		"canonicalEntityId",
		rankedFeedWindowEntityRefMaxBytes,
		0,
		0,
	)
	assertCanonicalOwnerBudget(t, entityFields, "title", 512, 0, 0)
	assertCanonicalOwnerBudget(t, entityFields, "categoryTags", 0, 20, 256)
	assertCanonicalOwnerBudget(t, entityFields, "coverUrl", 4096, 0, 0)
}

type canonicalOwnerBudgetField struct {
	Name             string   `yaml:"name"`
	Type             string   `yaml:"type"`
	Constraints      []string `yaml:"constraints"`
	MaxUTF8Bytes     int      `yaml:"max_utf8_bytes"`
	MaxItems         int      `yaml:"max_items"`
	ItemMaxUTF8Bytes int      `yaml:"item_max_utf8_bytes"`
}

func readCanonicalOwnerBudgetFields(
	t *testing.T,
	path string,
) map[string]canonicalOwnerBudgetField {
	t.Helper()
	raw, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read canonical owner fields %s: %v", path, err)
	}
	var document struct {
		Fields []canonicalOwnerBudgetField `yaml:"fields"`
	}
	if err := yaml.Unmarshal(raw, &document); err != nil {
		t.Fatalf("decode canonical owner fields %s: %v", path, err)
	}
	fields := make(map[string]canonicalOwnerBudgetField, len(document.Fields))
	for _, field := range document.Fields {
		fields[field.Name] = field
	}
	return fields
}

func assertCanonicalOwnerBudget(
	t *testing.T,
	fields map[string]canonicalOwnerBudgetField,
	name string,
	maxUTF8Bytes int,
	maxItems int,
	itemMaxUTF8Bytes int,
) {
	t.Helper()
	field, ok := fields[name]
	if !ok {
		t.Fatalf("canonical owner field %q is missing", name)
	}
	if field.MaxUTF8Bytes != maxUTF8Bytes ||
		field.MaxItems != maxItems ||
		field.ItemMaxUTF8Bytes != itemMaxUTF8Bytes {
		t.Fatalf(
			"canonical owner field %q budget=%+v, want bytes=%d items=%d item_bytes=%d",
			name,
			field,
			maxUTF8Bytes,
			maxItems,
			itemMaxUTF8Bytes,
		)
	}
}

func TestRankedFeedWindowTrainingMapsStayWithinModelFeatureRegistry(t *testing.T) {
	type feature struct {
		Name        string `yaml:"name"`
		Description string `yaml:"description"`
	}
	var registry struct {
		Scenarios map[string]struct {
			UserFeatures []feature `yaml:"user_features"`
			ItemFeatures []feature `yaml:"item_features"`
		} `yaml:"scenarios"`
	}
	registryPath := filepath.Join(
		"..", "..", "services", "recommendation-service", "internal", "recommendation",
		"recommendation_model_release", "infrastructure", "model_runtime", "scripts", "feature_registry.yaml",
	)
	raw, err := os.ReadFile(registryPath)
	if err != nil {
		t.Fatalf("read model feature registry: %v", err)
	}
	if err := yaml.Unmarshal(raw, &registry); err != nil {
		t.Fatalf("decode model feature registry: %v", err)
	}
	contentFeed, ok := registry.Scenarios["content_feed"]
	if !ok {
		t.Fatal("model feature registry omits content_feed")
	}
	userNames := make(map[string]feature, len(contentFeed.UserFeatures))
	for _, item := range contentFeed.UserFeatures {
		userNames[item.Name] = item
	}
	itemNames := make(map[string]struct{}, len(contentFeed.ItemFeatures))
	for _, item := range contentFeed.ItemFeatures {
		itemNames[item.Name] = struct{}{}
	}

	candidate := CandidateInput{ContentID: "post-registry", ContentType: "image", AuthorID: "author-registry"}
	snapshot := newTrainingFeatureSnapshot(&UserFeatureVector{}, candidate, time.Now().UTC())
	if snapshot.validationErr != nil {
		t.Fatalf("build registry snapshot: %v", snapshot.validationErr)
	}
	if len(snapshot.userFeatures) != rankedFeedWindowMaxUserFeatureKeys ||
		len(snapshot.itemFeatures) != rankedFeedWindowMaxItemFeatureKeys {
		t.Fatalf(
			"training map cardinality drifted: user=%d item=%d",
			len(snapshot.userFeatures),
			len(snapshot.itemFeatures),
		)
	}
	derivedMatchedEdge := map[string]struct{}{
		"intersectionEdgeWeight": {}, "intersectionEdgeFreshness": {}, "intersectionEdgeKind": {},
	}
	for name := range snapshot.userFeatures {
		if _, registered := userNames[name]; registered {
			continue
		}
		if _, derived := derivedMatchedEdge[name]; !derived {
			t.Fatalf("training user feature %q is absent from registry and matched-edge projection", name)
		}
	}
	for name := range snapshot.itemFeatures {
		if _, registered := itemNames[name]; !registered {
			t.Fatalf("training item feature %q is absent from registry", name)
		}
	}
	depth, ok := userNames["depthDistribution"]
	if !ok || !strings.Contains(depth.Description, "L0-L4") {
		t.Fatalf("depthDistribution registry no longer declares L0-L4: %+v", depth)
	}
}

func TestRankedFeedWindowEntryAdmissionRejectsOnlyContractProvenOverBudgetShapes(t *testing.T) {
	createdAt := time.Date(2026, 7, 29, 1, 0, 0, 0, time.UTC)
	validCandidate := CandidateInput{
		ContentID: "post-budget", ContentType: "article", AuthorID: "author-budget",
		Tags: []string{"Topic/旅行"}, EntityRefs: []string{"entity:homepage:place"},
	}
	validItem := FeedItem{
		ContentID: validCandidate.ContentID, ContentType: validCandidate.ContentType,
		AuthorID: validCandidate.AuthorID, Title: strings.Repeat("题", rankedFeedWindowTitleMaxRunes),
		Tags: validCandidate.Tags,
		trainingFeatures: newTrainingFeatureSnapshot(
			&UserFeatureVector{DepthDistribution: map[string]int{"L0": 1, "L4": 2}},
			validCandidate,
			createdAt,
		),
		rank: 1,
	}
	if _, err := newRankedFeedWindowItem(validItem, 1); err != nil {
		t.Fatalf("canonical boundary item rejected: %v", err)
	}

	t.Run("title", func(t *testing.T) {
		item := validItem
		item.Title += "题"
		_, err := newRankedFeedWindowItem(item, 1)
		if !errors.Is(err, ErrRankedFeedWindowEntryBudget) {
			t.Fatalf("overlong title error=%v, want entry budget", err)
		}
	})

	t.Run("projected refs", func(t *testing.T) {
		candidate := validCandidate
		candidate.Tags = make([]string, rankedFeedWindowMaxProjectedRefs)
		for index := range candidate.Tags {
			candidate.Tags[index] = "Topic/预算/标签"
		}
		candidate.EntityRefs = []string{"entity:homepage:overflow"}
		item := validItem
		item.Tags = candidate.Tags
		item.trainingFeatures = newTrainingFeatureSnapshot(nil, candidate, createdAt)
		_, err := newRankedFeedWindowItem(item, 1)
		if !errors.Is(err, ErrRankedFeedWindowEntryBudget) {
			t.Fatalf("over-budget refs error=%v, want entry budget", err)
		}
	})

	t.Run("depth registry", func(t *testing.T) {
		item := validItem
		item.trainingFeatures = newTrainingFeatureSnapshot(
			&UserFeatureVector{DepthDistribution: map[string]int{"L5": 1}},
			validCandidate,
			createdAt,
		)
		if len(item.trainingFeatures.userFeatures) != 0 {
			t.Fatal("invalid unbounded depth map was cloned into snapshot")
		}
		_, err := newRankedFeedWindowItem(item, 1)
		if !errors.Is(err, ErrRankedFeedWindowEntryBudget) {
			t.Fatalf("unregistered depth error=%v, want entry budget", err)
		}
	})

	t.Run("feature map", func(t *testing.T) {
		entry, err := newRankedFeedWindowItem(validItem, 1)
		if err != nil {
			t.Fatal(err)
		}
		delete(entry.Training.UserFeatures, "engagementRate")
		entry.Training.UserFeatures["unregisteredFeature"] = map[string]float64{"unbounded": 1}
		err = validateRankedFeedWindowEntryBudget(entry)
		if err == nil || !strings.Contains(err.Error(), "unregistered key") {
			t.Fatalf("unregistered feature error=%v", err)
		}
	})
}

func TestRankedFeedWindowStringEnvelopeRejectsBeforeOversizedItemJSON(t *testing.T) {
	createdAt := time.Date(2026, 7, 29, 2, 0, 0, 0, time.UTC)
	// ContentID appears in both the wire item and immutable training snapshot.
	// Each individual copy is smaller than 2 MiB, but encoding the entry would
	// already exceed the entire canonical window envelope.
	contentID := strings.Repeat("p", RankedFeedWindowMaxPayloadBytes/2+1)
	candidate := CandidateInput{
		ContentID:   contentID,
		ContentType: "article",
		AuthorID:    "author-string-envelope",
	}
	item := FeedItem{
		ContentID:        contentID,
		ContentType:      candidate.ContentType,
		AuthorID:         candidate.AuthorID,
		trainingFeatures: newTrainingFeatureSnapshot(nil, candidate, createdAt),
	}
	_, err := newRankedFeedWindowItem(item, 1)
	if !errors.Is(err, ErrRankedFeedWindowEntryBudget) ||
		!strings.Contains(err.Error(), "content.Post._id exceeds canonical 256-byte maximum") {
		t.Fatalf("oversized string envelope error=%v", err)
	}
}

func TestRankedFeedJSONStringBytesMatchesEncodingJSON(t *testing.T) {
	for _, value := range []string{
		"plain",
		"quote\\\"newline\n",
		"<script>&",
		"中文\u2028line\u2029separator",
		string([]byte{'a', 0xff, 'b'}),
	} {
		encoded, err := json.Marshal(value)
		if err != nil {
			t.Fatal(err)
		}
		if got := rankedFeedJSONStringBytes(value); got != len(encoded) {
			t.Fatalf("escaped bytes=%d, want=%d for %q (%s)", got, len(encoded), value, encoded)
		}
	}
}
