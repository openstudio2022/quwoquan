package publicweb

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"strings"
)

const defaultFetchLimit int64 = 2 << 20

type Service struct {
	resolver TargetResolver
	fetcher  NetworkFetcher
	store    EvidenceStore
	budget   BudgetGate
	parser   DocumentParser
}

func NewService(
	resolver TargetResolver,
	fetcher NetworkFetcher,
	store EvidenceStore,
	budget BudgetGate,
	parser DocumentParser,
) *Service {
	if resolver == nil || fetcher == nil || store == nil || budget == nil {
		panic("public web service dependencies are required")
	}
	if parser.MaxLinks <= 0 {
		parser = DefaultDocumentParser()
	}
	return &Service{
		resolver: resolver,
		fetcher:  fetcher,
		store:    store,
		budget:   budget,
		parser:   parser,
	}
}

func (s *Service) Open(ctx context.Context, request OpenRequest) (Document, error) {
	runID := strings.TrimSpace(request.RunID)
	if runID == "" || strings.TrimSpace(request.Target.Value) == "" {
		return Document{}, ErrInvalidTarget
	}
	resolved, err := s.resolver.ResolveTarget(ctx, runID, request.Target)
	if err != nil {
		if errors.Is(err, ErrEvidenceUnavailable) {
			return Document{}, err
		}
		return Document{}, fmt.Errorf("%w: %v", ErrTargetUnavailable, err)
	}
	reservation, err := s.budget.ReserveFetch(ctx, runID, defaultFetchLimit)
	if err != nil {
		if !errors.Is(err, ErrBudgetExhausted) {
			return Document{}, fmt.Errorf("%w: %v", ErrBudgetUnavailable, err)
		}
		return Document{}, fmt.Errorf("%w: %v", ErrBudgetExhausted, err)
	}
	committed := false
	defer func() {
		if !committed {
			reservation.Release()
		}
	}()

	result, err := s.fetcher.Fetch(ctx, NetworkRequest{
		URL:      resolved.URL,
		Method:   request.Method,
		MaxBytes: reservation.AllowedBytes(),
	})
	if err != nil {
		return Document{}, err
	}
	if err := reservation.Commit(int64(len(result.Body))); err != nil {
		if !errors.Is(err, ErrBudgetExhausted) {
			return Document{}, fmt.Errorf("%w: %v", ErrBudgetUnavailable, err)
		}
		return Document{}, fmt.Errorf("%w: %v", ErrBudgetExhausted, err)
	}
	committed = true

	digest := sha256.Sum256(result.Body)
	digestText := hex.EncodeToString(digest[:])
	targetID := deterministicIdentifier(
		"target",
		runID,
		string(request.Target.Kind),
		strings.TrimSpace(request.Target.Value),
		resolved.URL,
	)
	sourceID := deterministicIdentifier(
		"src",
		runID,
		targetID,
		result.FinalURL,
		digestText,
	)
	documentID := deterministicIdentifier("doc", runID, sourceID, digestText)
	artifactID := deterministicIdentifier("artifact", runID, digestText)
	artifactRef := "sha256:" + digestText
	parsed, err := s.parser.Parse(result.FinalURL, result.ContentType, result.Body)
	if err != nil {
		return Document{}, fmt.Errorf("%w: %v", ErrTargetRejected, err)
	}
	links := make([]DocumentLink, 0, len(parsed.Links))
	for _, link := range parsed.Links {
		links = append(links, DocumentLink{
			LinkID: deterministicLinkID(sourceID, link.URL),
			Title:  link.Title,
			Target: Target{Kind: TargetURL, Value: link.URL},
		})
	}
	document := Document{
		DocumentID: documentID,
		TargetID:   targetID,
		Target:     request.Target,
		Source: SourceLedgerEntry{
			SourceID:       sourceID,
			TargetID:       targetID,
			Origin:         resolved.Origin,
			ParentSourceID: resolved.ParentSourceID,
			RunID:          runID,
			SkillID:        strings.TrimSpace(request.SkillID),
			NormalizedURL:  result.FinalURL,
			RedirectChain:  append([]string{}, result.RedirectChain...),
			ContentDigest:  digestText,
			FetchedAt:      result.FetchedAt,
		},
		Title:         parsed.Title,
		ContentText:   parsed.Text,
		ContentDigest: digestText,
		ContentType:   result.ContentType,
		FetchedAt:     result.FetchedAt,
		Links:         links,
		ArtifactRef:   artifactRef,
		Untrusted:     true,
	}
	if err := s.store.CommitEvidence(ctx, EvidenceRecord{
		Target: TargetLedgerEntry{
			TargetID:       targetID,
			RunID:          runID,
			Requested:      request.Target,
			ResolvedURL:    resolved.URL,
			Origin:         resolved.Origin,
			ParentSourceID: resolved.ParentSourceID,
			ResolvedAt:     result.FetchedAt,
		},
		Source:   document.Source,
		Document: document,
		Artifact: Artifact{
			ArtifactID:    artifactID,
			ArtifactRef:   artifactRef,
			RunID:         runID,
			ContentDigest: digestText,
			ContentType:   result.ContentType,
			ByteLength:    int64(len(result.Body)),
			Body:          append([]byte{}, result.Body...),
			FetchedAt:     result.FetchedAt,
			Untrusted:     true,
		},
	}); err != nil {
		return Document{}, fmt.Errorf("%w: %v", ErrEvidenceCommit, err)
	}
	return document, nil
}

func deterministicIdentifier(prefix string, values ...string) string {
	digest := sha256.New()
	for _, value := range values {
		_, _ = digest.Write([]byte(value))
		_, _ = digest.Write([]byte{0})
	}
	return prefix + "_" + hex.EncodeToString(digest.Sum(nil)[:16])
}

func deterministicLinkID(sourceID, targetURL string) string {
	digest := sha256.Sum256([]byte(sourceID + "\x00" + targetURL))
	return "link_" + hex.EncodeToString(digest[:12])
}
