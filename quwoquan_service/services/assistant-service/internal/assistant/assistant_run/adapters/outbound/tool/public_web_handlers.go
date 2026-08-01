package tool

import (
	"context"
	"errors"
	"net/url"
	"strings"
	"time"

	rtfailures "quwoquan_service/runtime/failures"
	runerrors "quwoquan_service/services/assistant-service/generated/assistant/assistant_run"
	publicweb "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/publicweb"
	toolpkg "quwoquan_service/services/assistant-service/internal/assistant/assistant_session/application/tool"
)

const publicWebToolExcerptRunes = 20_000

func SearchHandler(
	delegate toolpkg.Handler,
	ledger publicweb.DiscoveryLedger,
) toolpkg.Handler {
	if delegate == nil || ledger == nil {
		panic("public web search handler dependencies are required")
	}
	return func(ctx context.Context, request toolpkg.Request) (
		toolResult toolpkg.Result,
		handlerErr error,
	) {
		started := time.Now()
		defer func() { observePublicWebTool("web_search", started, handlerErr) }()
		delegateResult, err := delegate(ctx, request)
		if err != nil {
			return toolpkg.Result{}, err
		}
		rawReferences, _ := delegateResult.Output["references"].([]map[string]any)
		references := make([]publicweb.SearchReference, 0, len(rawReferences))
		for _, reference := range rawReferences {
			destination, _ := reference["destination"].(map[string]any)
			references = append(references, publicweb.SearchReference{
				Title:   stringInput(reference, "title"),
				URL:     stringInput(destination, "url"),
				Source:  stringInput(reference, "source"),
				Snippet: stringInput(reference, "snippet"),
			})
		}
		discovered, err := ledger.RecordSearchReferences(
			ctx,
			stringInput(request.Input, "runId"),
			references,
		)
		if err != nil {
			return toolpkg.Result{}, canonicalPublicWebFailure(
				publicweb.ErrEvidenceUnavailable,
			)
		}
		byURL := make(map[string]string, len(discovered))
		for _, source := range discovered {
			byURL[source.NormalizedURL] = source.SourceID
		}
		enriched := make([]map[string]any, 0, len(rawReferences))
		for _, reference := range rawReferences {
			clone := cloneMap(reference)
			destination, _ := clone["destination"].(map[string]any)
			if sourceID := byURL[normalizedReferenceURL(stringInput(destination, "url"))]; sourceID != "" {
				clone["sourceId"] = sourceID
			}
			enriched = append(enriched, clone)
		}
		output := cloneMap(delegateResult.Output)
		output["references"] = enriched
		sourceIDs := make([]string, 0, len(discovered))
		for _, source := range discovered {
			sourceIDs = append(sourceIDs, source.SourceID)
		}
		reliable, _ := output["reliable"].(bool)
		output["evidenceAssessment"] = assessmentProjection(
			publicweb.AssessSearchEvidence(reliable, sourceIDs),
		)
		return toolpkg.Result{Output: output}, nil
	}
}

func OpenHandler(service *publicweb.Service) toolpkg.Handler {
	if service == nil {
		panic("public web service is required")
	}
	return func(ctx context.Context, request toolpkg.Request) (
		toolResult toolpkg.Result,
		handlerErr error,
	) {
		started := time.Now()
		defer func() { observePublicWebTool("web_open", started, handlerErr) }()
		target, err := webTarget(request.Input["target"])
		if err != nil {
			return toolpkg.Result{}, canonicalPublicWebFailure(err)
		}
		document, err := service.Open(ctx, publicweb.OpenRequest{
			RunID:   stringInput(request.Input, "runId"),
			SkillID: stringInput(request.Input, "skillId"),
			Target:  target,
			Method:  "GET",
		})
		if err != nil {
			return toolpkg.Result{}, canonicalPublicWebFailure(err)
		}
		return toolpkg.Result{Output: map[string]any{
			"document":           documentProjection(document),
			"reference":          referenceProjection(document),
			"evidenceAssessment": assessmentProjection(publicweb.AssessOpenEvidence(document)),
		}}, nil
	}
}

func canonicalPublicWebFailure(cause error) error {
	switch {
	case errors.Is(cause, publicweb.ErrInvalidTarget),
		errors.Is(cause, publicweb.ErrTargetUnavailable),
		errors.Is(cause, publicweb.ErrTargetRejected):
		return toolpkg.CanonicalFailure{
			Code:      runerrors.ErrWebTargetRejected.Error(),
			Origin:    rtfailures.OriginUser,
			Kind:      rtfailures.KindPermission,
			Nature:    rtfailures.NaturePermanent,
			Reason:    "web_target_rejected",
			Retryable: false,
			Cause:     cause,
		}
	case errors.Is(cause, publicweb.ErrBudgetExhausted):
		return toolpkg.CanonicalFailure{
			Code:      runerrors.ErrWebBudgetExhausted.Error(),
			Origin:    rtfailures.OriginEnvironment,
			Kind:      rtfailures.KindRateLimited,
			Nature:    rtfailures.NaturePermanent,
			Reason:    "web_budget_exhausted",
			Retryable: false,
			Cause:     cause,
		}
	case errors.Is(cause, publicweb.ErrBudgetUnavailable):
		return toolpkg.CanonicalFailure{
			Code:      runerrors.ErrWebBudgetUnavailable.Error(),
			Origin:    rtfailures.OriginSystem,
			Kind:      rtfailures.KindStorage,
			Nature:    rtfailures.NatureTransient,
			Reason:    "web_budget_unavailable",
			Retryable: true,
			Cause:     cause,
		}
	case errors.Is(cause, publicweb.ErrEvidenceCommit),
		errors.Is(cause, publicweb.ErrEvidenceUnavailable):
		return toolpkg.CanonicalFailure{
			Code:      runerrors.ErrWebEvidenceUnavailable.Error(),
			Origin:    rtfailures.OriginSystem,
			Kind:      rtfailures.KindStorage,
			Nature:    rtfailures.NatureTransient,
			Reason:    "web_evidence_unavailable",
			Retryable: true,
			Cause:     cause,
		}
	default:
		return toolpkg.CanonicalFailure{
			Code:      runerrors.ErrWebFetchUnavailable.Error(),
			Origin:    rtfailures.OriginRemoteDependency,
			Kind:      rtfailures.KindNetwork,
			Nature:    rtfailures.NatureTransient,
			Reason:    "web_fetch_unavailable",
			Retryable: true,
			Cause:     cause,
		}
	}
}

func FindHandler(finder *publicweb.Finder) toolpkg.Handler {
	if finder == nil {
		panic("public web finder is required")
	}
	return func(ctx context.Context, request toolpkg.Request) (
		toolResult toolpkg.Result,
		handlerErr error,
	) {
		started := time.Now()
		defer func() { observePublicWebTool("web_find", started, handlerErr) }()
		findResult, err := finder.Find(ctx, publicweb.FindRequest{
			RunID:      stringInput(request.Input, "runId"),
			DocumentID: stringInput(request.Input, "documentId"),
			Pattern:    stringInput(request.Input, "pattern"),
			MaxMatches: intInput(request.Input, "maxMatches"),
		})
		if err != nil {
			return toolpkg.Result{}, canonicalPublicWebFailure(err)
		}
		matches := make([]map[string]any, 0, len(findResult.Matches))
		for _, match := range findResult.Matches {
			matches = append(matches, map[string]any{
				"lineNumber": match.LineNumber,
				"snippet":    match.Snippet,
			})
		}
		return toolpkg.Result{Output: map[string]any{
			"result": map[string]any{
				"documentId":  findResult.DocumentID,
				"sourceId":    findResult.SourceID,
				"artifactRef": findResult.ArtifactRef,
				"pattern":     findResult.Pattern,
				"matches":     matches,
				"untrusted":   true,
			},
			"reference": map[string]any{
				"sourceId": findResult.SourceID,
				"source":   publicWebSource(findResult.NormalizedURL),
				"destination": map[string]any{
					"kind": "external",
					"url":  findResult.NormalizedURL,
				},
			},
			"evidenceAssessment": assessmentProjection(
				publicweb.AssessFindEvidence(findResult),
			),
		}}, nil
	}
}

func webTarget(value any) (publicweb.Target, error) {
	raw, ok := value.(map[string]any)
	if !ok {
		return publicweb.Target{}, publicweb.ErrInvalidTarget
	}
	target := publicweb.Target{
		Kind:  publicweb.TargetKind(stringInput(raw, "kind")),
		Value: stringInput(raw, "value"),
	}
	if target.Value == "" {
		return publicweb.Target{}, publicweb.ErrInvalidTarget
	}
	return target, nil
}

func documentProjection(document publicweb.Document) map[string]any {
	links := make([]map[string]any, 0, len(document.Links))
	for _, link := range document.Links {
		links = append(links, map[string]any{
			"linkId": link.LinkID,
			"title":  link.Title,
		})
	}
	content, truncated := boundedRunes(document.ContentText, publicWebToolExcerptRunes)
	return map[string]any{
		"documentId":    document.DocumentID,
		"targetId":      document.TargetID,
		"title":         document.Title,
		"contentText":   content,
		"contentDigest": document.ContentDigest,
		"contentType":   document.ContentType,
		"fetchedAt":     document.FetchedAt.UTC().Format("2006-01-02T15:04:05.000Z"),
		"links":         links,
		"artifactRef":   document.ArtifactRef,
		"untrusted":     true,
		"truncated":     truncated,
	}
}

func referenceProjection(document publicweb.Document) map[string]any {
	return map[string]any{
		"sourceId":       document.Source.SourceID,
		"targetId":       document.Source.TargetID,
		"parentSourceId": document.Source.ParentSourceID,
		"source":         publicWebSource(document.Source.NormalizedURL),
		"title":          document.Title,
		"contentDigest":  document.ContentDigest,
		"fetchedAt":      document.FetchedAt.UTC().Format("2006-01-02T15:04:05.000Z"),
		"destination": map[string]any{
			"kind": "external",
			"url":  document.Source.NormalizedURL,
		},
	}
}

func publicWebSource(rawURL string) string {
	parsed, err := url.Parse(strings.TrimSpace(rawURL))
	if err != nil {
		return ""
	}
	return strings.ToLower(parsed.Hostname())
}

func assessmentProjection(assessment publicweb.EvidenceAssessment) map[string]any {
	return map[string]any{
		"status":             string(assessment.Status),
		"evidenceSufficient": assessment.EvidenceSufficient,
		"replanRequired":     assessment.ReplanRequired,
		"reason":             assessment.Reason,
		"targetIds":          append([]string{}, assessment.TargetIDs...),
		"documentIds":        append([]string{}, assessment.DocumentIDs...),
		"artifactRefs":       append([]string{}, assessment.ArtifactRefs...),
		"sourceIds":          append([]string{}, assessment.SourceIDs...),
	}
}

func stringInput(input map[string]any, key string) string {
	value, _ := input[key].(string)
	return strings.TrimSpace(value)
}

func intInput(input map[string]any, key string) int {
	switch value := input[key].(type) {
	case int:
		return value
	case float64:
		return int(value)
	default:
		return 0
	}
}

func boundedRunes(value string, limit int) (string, bool) {
	runes := []rune(value)
	if len(runes) <= limit {
		return value, false
	}
	return string(runes[:limit]), true
}

func cloneMap(value map[string]any) map[string]any {
	clone := make(map[string]any, len(value))
	for key, item := range value {
		if nested, ok := item.(map[string]any); ok {
			clone[key] = cloneMap(nested)
			continue
		}
		clone[key] = item
	}
	return clone
}

func normalizedReferenceURL(raw string) string {
	parsed, err := url.Parse(strings.TrimSpace(raw))
	if err != nil {
		return ""
	}
	parsed.Fragment = ""
	return parsed.String()
}
