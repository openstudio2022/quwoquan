package application

import (
	"bufio"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"time"
)

// BulkImportItem represents a single item from a release manifest NDJSON line.
type BulkImportItem struct {
	PostID      string   `json:"postId"`
	Title       string   `json:"title"`
	ContentType string   `json:"contentType"`
	AuthorID    string   `json:"authorId"`
	Tags        []string `json:"tags"`
	EntityRefs  []string `json:"entityRefs"`
	PublishedAt string   `json:"publishedAt"`
	CoverURL    string   `json:"coverUrl"`
	BodyLength  int      `json:"bodyLength"`
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
