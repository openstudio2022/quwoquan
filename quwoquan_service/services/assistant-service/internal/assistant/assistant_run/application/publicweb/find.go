package publicweb

import (
	"context"
	"errors"
	"strings"
)

type DocumentReader interface {
	ReadDocument(context.Context, string, string) (Document, error)
}

type FindRequest struct {
	RunID      string
	DocumentID string
	Pattern    string
	MaxMatches int
}

type FindMatch struct {
	LineNumber int
	Snippet    string
}

type FindResult struct {
	DocumentID    string
	SourceID      string
	ArtifactRef   string
	NormalizedURL string
	Pattern       string
	Matches       []FindMatch
	Untrusted     bool
}

type Finder struct {
	documents DocumentReader
}

func NewFinder(documents DocumentReader) *Finder {
	if documents == nil {
		panic("public web document reader is required")
	}
	return &Finder{documents: documents}
}

func (f *Finder) Find(ctx context.Context, request FindRequest) (FindResult, error) {
	pattern := strings.TrimSpace(request.Pattern)
	if strings.TrimSpace(request.RunID) == "" || strings.TrimSpace(request.DocumentID) == "" ||
		pattern == "" || len([]rune(pattern)) > 256 {
		return FindResult{}, ErrInvalidTarget
	}
	document, err := f.documents.ReadDocument(ctx, request.RunID, request.DocumentID)
	if err != nil {
		return FindResult{}, err
	}
	if document.DocumentID != request.DocumentID || document.Source.RunID != request.RunID {
		return FindResult{}, errors.New("public web document is not owned by run")
	}
	limit := request.MaxMatches
	if limit <= 0 || limit > 20 {
		limit = 20
	}
	needle := strings.ToLower(pattern)
	matches := make([]FindMatch, 0, limit)
	for index, line := range strings.Split(document.ContentText, "\n") {
		if !strings.Contains(strings.ToLower(line), needle) {
			continue
		}
		matches = append(matches, FindMatch{
			LineNumber: index + 1,
			Snippet:    boundedSnippet(line, 360),
		})
		if len(matches) == limit {
			break
		}
	}
	return FindResult{
		DocumentID:    document.DocumentID,
		SourceID:      document.Source.SourceID,
		ArtifactRef:   document.ArtifactRef,
		NormalizedURL: document.Source.NormalizedURL,
		Pattern:       pattern,
		Matches:       matches,
		Untrusted:     true,
	}, nil
}

func boundedSnippet(value string, limit int) string {
	value = strings.TrimSpace(value)
	runes := []rune(value)
	if len(runes) <= limit {
		return value
	}
	return string(runes[:limit]) + "…"
}
