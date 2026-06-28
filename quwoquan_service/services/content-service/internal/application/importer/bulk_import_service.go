package importer

import (
	"bufio"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"strings"
	"time"

	postsemantic "quwoquan_service/services/content-service/internal/domain/post/semantic"
)

// BulkImportItem represents a single item from a release manifest NDJSON line.
type BulkImportItem struct {
	PostID                string         `json:"postId"`
	Title                 string         `json:"title"`
	ContentType           string         `json:"contentType"`
	AuthorID              string         `json:"authorId"`
	CreatorProfileID      string         `json:"creatorProfileId"`
	CreatorArchetype      string         `json:"creatorArchetype"`
	CreatorProfileVersion string         `json:"creatorProfileVersion"`
	CreatorDisclosure     map[string]any `json:"creatorDisclosure"`
	ExperienceClaimMode   string         `json:"experienceClaimMode"`
	AuthorQualitySignals  map[string]any `json:"authorQualitySignals"`
	Tags                  []string       `json:"tags"`
	EntityRefs            []string       `json:"entityRefs"`
	SemanticMentions      any            `json:"semanticMentions"`
	PublishedAt           string         `json:"publishedAt"`
	CoverURL              string         `json:"coverUrl"`
	BodyLength            int            `json:"bodyLength"`
	// SourceTaskID 内容溯源任务 id；ConditionProfile 条件画像 {regions/seasons/altitudeMeters}（从主实体冗余）。
	SourceTaskID     string         `json:"sourceTaskId"`
	ConditionProfile map[string]any `json:"conditionProfile"`
}

func (item BulkImportItem) systemAuthorContent() bool {
	authorID := strings.TrimSpace(item.AuthorID)
	return strings.HasPrefix(authorID, "agent_author_") || strings.HasPrefix(authorID, "builtin_") ||
		strings.HasPrefix(strings.TrimSpace(item.CreatorProfileID), "agent_creator_") ||
		strings.HasPrefix(strings.TrimSpace(item.CreatorProfileID), "qwq_creator_")
}

func validateCreatorProjection(item BulkImportItem) error {
	if !item.systemAuthorContent() {
		return nil
	}
	if strings.TrimSpace(item.AuthorID) == "" {
		return fmt.Errorf("system creator content missing authorId")
	}
	if strings.TrimSpace(item.CreatorProfileID) == "" {
		return fmt.Errorf("system creator content missing creatorProfileId")
	}
	if strings.TrimSpace(item.CreatorArchetype) == "" {
		return fmt.Errorf("system creator content missing creatorArchetype")
	}
	if strings.TrimSpace(item.CreatorProfileVersion) == "" {
		return fmt.Errorf("system creator content missing creatorProfileVersion")
	}
	if strings.TrimSpace(item.ExperienceClaimMode) == "" {
		return fmt.Errorf("system creator content missing experienceClaimMode")
	}
	if item.CreatorDisclosure == nil {
		return fmt.Errorf("system creator content missing creatorDisclosure")
	}
	if item.CreatorDisclosure["type"] != "platform_virtual_creator" {
		return fmt.Errorf("system creator content creatorDisclosure.type must be platform_virtual_creator")
	}
	if item.CreatorDisclosure["visible"] != true {
		return fmt.Errorf("system creator content creatorDisclosure.visible must be true")
	}
	if strings.TrimSpace(fmt.Sprint(item.CreatorDisclosure["displayText"])) == "" {
		return fmt.Errorf("system creator content creatorDisclosure.displayText is required")
	}
	return nil
}

// BulkImportStore persists imported items to the discovery feed collection.
type BulkImportStore interface {
	UpsertDiscoveryFeedItem(ctx context.Context, item BulkImportItem) error
	UpsertEntityTags(ctx context.Context, entityID string, tags []string) error
}

// BulkImportService handles importing release manifests into the content service.
type BulkImportService struct {
	store BulkImportStore
}

func NewBulkImportService(store BulkImportStore) *BulkImportService {
	return &BulkImportService{store: store}
}

// ImportResult summarizes the outcome of a bulk import operation.
type ImportResult struct {
	Total    int
	Success  int
	Failed   int
	Duration time.Duration
}

// ImportNDJSON reads an NDJSON stream and upserts each item into the discovery feed.
func (s *BulkImportService) ImportNDJSON(ctx context.Context, reader io.Reader) (*ImportResult, error) {
	start := time.Now()
	scanner := bufio.NewScanner(reader)
	scanner.Buffer(make([]byte, 1024*1024), 1024*1024)

	result := &ImportResult{}

	for scanner.Scan() {
		line := scanner.Bytes()
		if len(line) == 0 {
			continue
		}

		var item BulkImportItem
		if err := json.Unmarshal(line, &item); err != nil {
			result.Failed++
			continue
		}

		if item.PostID == "" {
			result.Failed++
			continue
		}

		result.Total++
		if err := validateCreatorProjection(item); err != nil {
			result.Failed++
			continue
		}
		if err := postsemantic.ValidateSuppliedRefs(item.SemanticMentions, item.EntityRefs, item.Tags); err != nil {
			result.Failed++
			continue
		}
		if postsemantic.Present(item.SemanticMentions) {
			projection := postsemantic.Project(item.SemanticMentions)
			item.EntityRefs = projection.EntityRefs
			item.Tags = projection.TagRefs
		}
		if err := s.store.UpsertDiscoveryFeedItem(ctx, item); err != nil {
			result.Failed++
			continue
		}

		// Also index entity tags for the propagation chain
		for _, entityRef := range item.EntityRefs {
			_ = s.store.UpsertEntityTags(ctx, entityRef, item.Tags)
		}

		result.Success++
	}

	if err := scanner.Err(); err != nil {
		return result, fmt.Errorf("scan error: %w", err)
	}

	result.Duration = time.Since(start)
	return result, nil
}
