package recommendation

import (
	"fmt"
	"strings"
	"unicode/utf8"
)

// These admission constants are executable derivatives of the content Post
// publication contract. ranked_feed_window_entry_budget__local_contract_test
// locks them to publication_policy.yaml and fields.yaml; the contracts remain
// the owners and a drift fails the gate.
const (
	rankedFeedWindowTitleMaxRunes      = 80
	rankedFeedWindowContentIDMaxBytes  = 256
	rankedFeedWindowAuthorIDMaxBytes   = 128
	rankedFeedWindowTitleMaxBytes      = 320
	rankedFeedWindowTagRefMaxBytes     = 256
	rankedFeedWindowEntityRefMaxBytes  = 256
	rankedFeedWindowMaxProjectedRefs   = 30
	rankedFeedWindowMaxUserFeatureKeys = 27
	rankedFeedWindowMaxItemFeatureKeys = 22
)

var rankedFeedDepthLevels = map[string]struct{}{
	"L0": {},
	"L1": {},
	"L2": {},
	"L3": {},
	"L4": {},
}

func validateRankedFeedCandidateFeatureBudget(candidate CandidateInput) error {
	if err := validateRankedFeedOwnerText(
		"content.Post._id",
		candidate.ContentID,
		rankedFeedWindowContentIDMaxBytes,
		true,
	); err != nil {
		return err
	}
	if err := validateRankedFeedOwnerText(
		"user.Persona.personaId",
		candidate.AuthorID,
		rankedFeedWindowAuthorIDMaxBytes,
		false,
	); err != nil {
		return err
	}
	if len(candidate.Tags)+len(candidate.EntityRefs) > rankedFeedWindowMaxProjectedRefs {
		return fmt.Errorf(
			"tagRefs+entityRefs contains %d items; canonical maximum is %d",
			len(candidate.Tags)+len(candidate.EntityRefs),
			rankedFeedWindowMaxProjectedRefs,
		)
	}
	for _, tagRef := range candidate.Tags {
		if err := validateRankedFeedOwnerText(
			"tag.TagNodeView.tagRef",
			tagRef,
			rankedFeedWindowTagRefMaxBytes,
			true,
		); err != nil {
			return err
		}
	}
	for _, entityRef := range candidate.EntityRefs {
		if err := validateRankedFeedOwnerText(
			"entity.Homepage.canonicalEntityId",
			entityRef,
			rankedFeedWindowEntityRefMaxBytes,
			true,
		); err != nil {
			return err
		}
	}
	return nil
}

func validateRankedFeedDepthDistribution(distribution map[string]int) error {
	if len(distribution) > len(rankedFeedDepthLevels) {
		return fmt.Errorf("depthDistribution contains %d keys; maximum is %d", len(distribution), len(rankedFeedDepthLevels))
	}
	for level, count := range distribution {
		if _, ok := rankedFeedDepthLevels[level]; !ok {
			return fmt.Errorf("depthDistribution contains non-canonical level %q", level)
		}
		if count < 0 {
			return fmt.Errorf("depthDistribution level %q contains negative count", level)
		}
	}
	return nil
}

func validateRankedFeedWindowEntryBudget(entry rankedFeedWindowItem) error {
	if utf8.RuneCountInString(entry.Item.Title) > rankedFeedWindowTitleMaxRunes {
		return fmt.Errorf("title exceeds canonical %d-rune maximum", rankedFeedWindowTitleMaxRunes)
	}
	for _, text := range []struct {
		owner    string
		value    string
		maxBytes int
		required bool
	}{
		{"content.Post._id", entry.Item.ContentID, rankedFeedWindowContentIDMaxBytes, true},
		{"user.Persona.personaId", entry.Item.AuthorID, rankedFeedWindowAuthorIDMaxBytes, false},
		{"content.Post.title", entry.Item.Title, rankedFeedWindowTitleMaxBytes, false},
	} {
		if err := validateRankedFeedOwnerText(
			text.owner,
			text.value,
			text.maxBytes,
			text.required,
		); err != nil {
			return err
		}
	}
	if len(entry.Item.Tags) > rankedFeedWindowMaxProjectedRefs {
		return fmt.Errorf("feed item tagRefs contains %d items; maximum is %d", len(entry.Item.Tags), rankedFeedWindowMaxProjectedRefs)
	}
	for _, tagRef := range entry.Item.Tags {
		if err := validateRankedFeedOwnerText(
			"tag.TagNodeView.tagRef",
			tagRef,
			rankedFeedWindowTagRefMaxBytes,
			true,
		); err != nil {
			return err
		}
	}
	if err := validateRankedFeedTrainingSnapshotBudget(entry.Training, entry.Item); err != nil {
		return err
	}
	if _, err := consumeRankedFeedWindowEntryStringBytes(
		entry,
		RankedFeedWindowMaxPayloadBytes,
	); err != nil {
		return err
	}
	return nil
}

func validateRankedFeedOwnerText(
	owner string,
	value string,
	maximumBytes int,
	required bool,
) error {
	if !utf8.ValidString(value) {
		return fmt.Errorf("%s is not valid UTF-8", owner)
	}
	if required && strings.TrimSpace(value) == "" {
		return fmt.Errorf("%s is required", owner)
	}
	if len(value) > maximumBytes {
		return fmt.Errorf(
			"%s exceeds canonical %d-byte maximum",
			owner,
			maximumBytes,
		)
	}
	return nil
}

// consumeRankedFeedWindowEntryStringBytes proves that the JSON-escaped string
// contribution of one entry can fit inside the existing canonical 2 MiB
// window envelope before encoding/json is allowed to allocate an item chunk.
//
// Owner-specific field limits are enforced before this aggregate envelope and
// locked to content/user/tag/entity metadata by local_contract. This second
// bound closes the remaining allocation hole where many individually valid
// strings could make json.Marshal allocate a chunk larger than the whole Redis
// value budget before the incremental writer rejected it.
func consumeRankedFeedWindowEntryStringBytes(
	entry rankedFeedWindowItem,
	remaining int,
) (int, error) {
	consume := func(value string) bool {
		encodedBytes := rankedFeedJSONStringBytes(value)
		if encodedBytes > remaining {
			return false
		}
		remaining -= encodedBytes
		return true
	}
	for _, value := range []string{
		entry.Item.ContentID,
		entry.Item.ContentType,
		entry.Item.AuthorID,
		entry.Item.Title,
		entry.Item.RecallPath,
		entry.Item.ContentVertical,
		entry.Item.SupplySource,
		entry.SourceOwner,
		entry.ReleaseID,
		entry.ManifestDigest,
		entry.LifecycleStatus,
	} {
		if !consume(value) {
			return remaining, fmt.Errorf(
				"entry strings exceed canonical ranked-window %d-byte envelope",
				RankedFeedWindowMaxPayloadBytes,
			)
		}
	}
	for _, value := range entry.Item.Tags {
		if !consume(value) {
			return remaining, fmt.Errorf(
				"entry strings exceed canonical ranked-window %d-byte envelope",
				RankedFeedWindowMaxPayloadBytes,
			)
		}
	}
	var err error
	remaining, err = consumeRankedFeedFeatureMapStringBytes(
		entry.Training.UserFeatures,
		remaining,
	)
	if err != nil {
		return remaining, err
	}
	return consumeRankedFeedFeatureMapStringBytes(
		entry.Training.ItemFeatures,
		remaining,
	)
}

func validateRankedFeedWindowStringEnvelope(
	window rankedFeedWindow,
	maxBytes int,
) error {
	remaining := maxBytes
	consume := func(value string) error {
		encodedBytes := rankedFeedJSONStringBytes(value)
		if encodedBytes > remaining {
			return fmt.Errorf(
				"%w: JSON-escaped strings exceed bytes=%d",
				ErrRankedFeedWindowPayloadTooLarge,
				maxBytes,
			)
		}
		remaining -= encodedBytes
		return nil
	}
	for _, value := range []string{
		window.WindowID,
		window.Binding.SubjectHash,
		window.Binding.ActorID,
		window.Binding.PersonaID,
		window.Binding.SessionID,
		string(window.Binding.FeedType),
		window.Binding.Sort,
		window.Binding.Surface,
		window.Binding.ChannelID,
		window.Binding.Vertical,
		window.Binding.FeedRequestID,
		window.Binding.ReleaseID,
		window.Binding.ManifestDigest,
		window.Provenance.CandidateWatermark,
		window.Provenance.PolicyDigest,
		window.Provenance.ModelReleaseID,
		window.Provenance.FeatureSnapshotAt,
		window.Provenance.ScorerPath,
		window.Attribution.FeedRequestID,
		window.Attribution.PersonaID,
		window.Attribution.ChannelID,
		window.Attribution.ModelBucket,
		window.Attribution.ModelChannel,
		window.Attribution.ModelReleaseID,
		window.Attribution.ScoringBucket,
		window.Attribution.PolicyDigest,
		string(window.TerminalOutcome),
		string(window.FailureStage),
	} {
		if err := consume(value); err != nil {
			return err
		}
	}
	for _, entry := range window.Items {
		var err error
		remaining, err = consumeRankedFeedWindowEntryStringBytes(entry, remaining)
		if err != nil {
			return fmt.Errorf("%w: ordinal=%d: %v", ErrRankedFeedWindowPayloadTooLarge, entry.Ordinal, err)
		}
	}
	return nil
}

func consumeRankedFeedFeatureMapStringBytes(
	features map[string]any,
	remaining int,
) (int, error) {
	for key, value := range features {
		keyBytes := rankedFeedJSONStringBytes(key)
		if keyBytes > remaining {
			return remaining, fmt.Errorf(
				"training feature strings exceed canonical ranked-window %d-byte envelope",
				RankedFeedWindowMaxPayloadBytes,
			)
		}
		remaining -= keyBytes
		var err error
		remaining, err = consumeRankedFeedFeatureValueStringBytes(value, remaining)
		if err != nil {
			return remaining, err
		}
	}
	return remaining, nil
}

func consumeRankedFeedFeatureValueStringBytes(
	value any,
	remaining int,
) (int, error) {
	consume := func(text string) (int, error) {
		encodedBytes := rankedFeedJSONStringBytes(text)
		if encodedBytes > remaining {
			return remaining, fmt.Errorf(
				"training feature strings exceed canonical ranked-window %d-byte envelope",
				RankedFeedWindowMaxPayloadBytes,
			)
		}
		return remaining - encodedBytes, nil
	}
	switch typed := value.(type) {
	case nil, bool, int, int8, int16, int32, int64,
		uint, uint8, uint16, uint32, uint64, float32, float64:
		return remaining, nil
	case string:
		return consume(typed)
	case []string:
		var err error
		for _, item := range typed {
			remaining, err = consume(item)
			if err != nil {
				return remaining, err
			}
		}
		return remaining, nil
	case []any:
		var err error
		for _, item := range typed {
			remaining, err = consumeRankedFeedFeatureValueStringBytes(item, remaining)
			if err != nil {
				return remaining, err
			}
		}
		return remaining, nil
	case map[string]float64:
		for key := range typed {
			var err error
			remaining, err = consume(key)
			if err != nil {
				return remaining, err
			}
		}
		return remaining, nil
	case map[string]int:
		for key := range typed {
			var err error
			remaining, err = consume(key)
			if err != nil {
				return remaining, err
			}
		}
		return remaining, nil
	case map[string]any:
		return consumeRankedFeedFeatureMapStringBytes(typed, remaining)
	default:
		return remaining, fmt.Errorf(
			"training feature value has unsupported type %T",
			value,
		)
	}
}

// rankedFeedJSONStringBytes returns encoding/json's escaped string length,
// including the surrounding quotes, without allocating the escaped form.
func rankedFeedJSONStringBytes(value string) int {
	encodedBytes := 2
	for index := 0; index < len(value); {
		byteValue := value[index]
		if byteValue < utf8.RuneSelf {
			switch {
			case byteValue == '\\' || byteValue == '"' || byteValue == '\n' ||
				byteValue == '\r' || byteValue == '\t' || byteValue == '\b' ||
				byteValue == '\f':
				encodedBytes += 2
			case byteValue < 0x20 || byteValue == '<' || byteValue == '>' || byteValue == '&':
				encodedBytes += 6
			default:
				encodedBytes++
			}
			index++
			continue
		}
		runeValue, size := utf8.DecodeRuneInString(value[index:])
		switch {
		case runeValue == utf8.RuneError && size == 1:
			encodedBytes += 6
		case runeValue == '\u2028' || runeValue == '\u2029':
			encodedBytes += 6
		default:
			encodedBytes += size
		}
		index += size
	}
	return encodedBytes
}

func validateRankedFeedTrainingSnapshotBudget(
	snapshot rankedFeedTrainingSnapshot,
	item FeedItem,
) error {
	if len(snapshot.UserFeatures) > rankedFeedWindowMaxUserFeatureKeys {
		return fmt.Errorf("training userFeatures contains %d keys; registry maximum is %d", len(snapshot.UserFeatures), rankedFeedWindowMaxUserFeatureKeys)
	}
	if len(snapshot.ItemFeatures) > rankedFeedWindowMaxItemFeatureKeys {
		return fmt.Errorf("training itemFeatures contains %d keys; registry maximum is %d", len(snapshot.ItemFeatures), rankedFeedWindowMaxItemFeatureKeys)
	}
	tagRefs, ok := rankedFeedStringSlice(snapshot.ItemFeatures["tagRefs"])
	if !ok {
		return fmt.Errorf("training itemFeatures.tagRefs must be a string list")
	}
	entityRefs, ok := rankedFeedStringSlice(snapshot.ItemFeatures["entityRefs"])
	if !ok {
		return fmt.Errorf("training itemFeatures.entityRefs must be a string list")
	}
	if len(tagRefs)+len(entityRefs) > rankedFeedWindowMaxProjectedRefs {
		return fmt.Errorf(
			"training tagRefs+entityRefs contains %d items; canonical maximum is %d",
			len(tagRefs)+len(entityRefs),
			rankedFeedWindowMaxProjectedRefs,
		)
	}
	for _, tagRef := range tagRefs {
		if err := validateRankedFeedOwnerText(
			"tag.TagNodeView.tagRef",
			tagRef,
			rankedFeedWindowTagRefMaxBytes,
			true,
		); err != nil {
			return err
		}
	}
	for _, entityRef := range entityRefs {
		if err := validateRankedFeedOwnerText(
			"entity.Homepage.canonicalEntityId",
			entityRef,
			rankedFeedWindowEntityRefMaxBytes,
			true,
		); err != nil {
			return err
		}
	}
	if !rankedFeedStringSlicesEqual(item.Tags, tagRefs) {
		return fmt.Errorf("feed item tagRefs differ from immutable training snapshot")
	}
	for key, value := range snapshot.ItemFeatures {
		if !rankedFeedKnownItemFeature(key) {
			return fmt.Errorf("training itemFeatures contains unregistered key %q", key)
		}
		_ = value
	}
	for key, value := range snapshot.UserFeatures {
		switch key {
		case "tagAffinities", "topicAffinities", "audienceAffinities", "formatAffinities", "entityAffinities", "circleTagAffinities":
			if err := validateRankedFeedFeatureMapKeys(key, value, tagRefs, rankedFeedWindowMaxProjectedRefs); err != nil {
				return err
			}
		case "entityInstanceAffinities":
			if err := validateRankedFeedFeatureMapKeys(key, value, entityRefs, rankedFeedWindowMaxProjectedRefs); err != nil {
				return err
			}
		case "authorAffinities":
			if err := validateRankedFeedFeatureMapKeys(key, value, []string{item.AuthorID}, 1); err != nil {
				return err
			}
		case "typeENER":
			if err := validateRankedFeedFeatureMapKeys(key, value, []string{item.ContentType}, 1); err != nil {
				return err
			}
		case "depthDistribution":
			if err := validateRankedFeedDepthDistributionAny(value); err != nil {
				return err
			}
		default:
			if !rankedFeedKnownScalarUserFeature(key) {
				return fmt.Errorf("training userFeatures contains unregistered key %q", key)
			}
		}
	}
	return nil
}

func rankedFeedStringSlicesEqual(left, right []string) bool {
	if len(left) != len(right) {
		return false
	}
	for index := range left {
		if left[index] != right[index] {
			return false
		}
	}
	return true
}

func rankedFeedKnownItemFeature(key string) bool {
	switch key {
	case "contentId", "contentType", "authorId", "tagRefs", "entityRefs", "ageHours", "publishHour", "viewCount", "likeCount", "commentCount", "shareCount", "tagCount", "recallPath", "qualityScore", "contentVertical", "supplySource", "intersectionFactStrength", "intersectionFreshness", "affinityIntersectionScore", "intersectionSourceRefTop", "intersectionConfidenceLabel", "intersectionClass":
		return true
	default:
		return false
	}
}

func rankedFeedKnownScalarUserFeature(key string) bool {
	switch key {
	case "intersectionEdgeWeight", "intersectionEdgeFreshness", "intersectionEdgeKind", "engagementRate", "totalLikes", "totalShares", "totalEvents", "avgEngagementDepth", "socialInterestScore", "sharedFolloweesCount", "sharedCircleCount", "coCommentedCount", "coVisitedEntityCount", "followeeInObjectActive", "followeeViewingActive", "affinityIntersectionScore", "intersectionSourceRefTop":
		return true
	default:
		return false
	}
}

func validateRankedFeedDepthDistributionAny(value any) error {
	switch typed := value.(type) {
	case map[string]int:
		return validateRankedFeedDepthDistribution(typed)
	case map[string]any:
		if len(typed) > len(rankedFeedDepthLevels) {
			return fmt.Errorf("depthDistribution contains %d keys; maximum is %d", len(typed), len(rankedFeedDepthLevels))
		}
		for level, rawCount := range typed {
			if _, ok := rankedFeedDepthLevels[level]; !ok {
				return fmt.Errorf("depthDistribution contains non-canonical level %q", level)
			}
			count, ok := rawCount.(float64)
			if !ok || count < 0 || count != float64(int64(count)) {
				return fmt.Errorf("depthDistribution level %q is not a non-negative integer", level)
			}
		}
		return nil
	default:
		return fmt.Errorf("depthDistribution must be an L0-L4 integer map")
	}
}

func validateRankedFeedFeatureMapKeys(
	name string,
	value any,
	allowedKeys []string,
	maxItems int,
) error {
	keys, ok := rankedFeedMapKeys(value)
	if !ok {
		return fmt.Errorf("training userFeatures.%s must be a numeric map", name)
	}
	if len(keys) > maxItems {
		return fmt.Errorf("training userFeatures.%s contains %d keys; maximum is %d", name, len(keys), maxItems)
	}
	allowed := make(map[string]struct{}, len(allowedKeys))
	for _, key := range allowedKeys {
		allowed[strings.TrimSpace(key)] = struct{}{}
	}
	for _, key := range keys {
		if _, exists := allowed[key]; !exists {
			return fmt.Errorf("training userFeatures.%s contains key outside candidate projection", name)
		}
	}
	return nil
}

func rankedFeedMapKeys(value any) ([]string, bool) {
	switch typed := value.(type) {
	case map[string]float64:
		keys := make([]string, 0, len(typed))
		for key := range typed {
			keys = append(keys, key)
		}
		return keys, true
	case map[string]any:
		keys := make([]string, 0, len(typed))
		for key, raw := range typed {
			if _, ok := raw.(float64); !ok {
				return nil, false
			}
			keys = append(keys, key)
		}
		return keys, true
	default:
		return nil, false
	}
}

func rankedFeedStringSlice(value any) ([]string, bool) {
	switch typed := value.(type) {
	case nil:
		return nil, true
	case []string:
		return typed, true
	case []any:
		out := make([]string, 0, len(typed))
		for _, raw := range typed {
			text, ok := raw.(string)
			if !ok {
				return nil, false
			}
			out = append(out, text)
		}
		return out, true
	default:
		return nil, false
	}
}
