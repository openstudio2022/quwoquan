package behavior

import (
	"context"
	"strings"
	"time"

	rtimpact "quwoquan_service/runtime/impact"
	rtrec "quwoquan_service/runtime/recommendation"
	"quwoquan_service/services/content-service/internal/content/post/application/ports"
)

func authorImpactEventFromSignal(
	signal rtrec.BehaviorSignal,
	occurredAt time.Time,
) ports.AuthorImpactEvent {
	// behavior action → helpType 反查 rtimpact.BehaviorActionToHelpType
	// （源 registry.helpTypes[].behaviorActions）。未登记动作不产生影响力事件。
	helpType, ok := rtimpact.BehaviorActionToHelpType[strings.TrimSpace(signal.Action)]
	if !ok {
		return ports.AuthorImpactEvent{}
	}
	return ports.AuthorImpactEvent{
		AuthorID:              strings.TrimSpace(signal.AuthorID),
		Action:                strings.TrimSpace(signal.Action),
		HelpType:              helpType,
		IntersectionDimension: strings.TrimSpace(signal.IntersectionDimension),
		IntersectionTagRefs:   signal.IntersectionTagRefs,
		Source:                "behavior",
		OccurredAt:            occurredAt,
	}
}

// authorImpactEvidenceSource is the canonical source tag for behavior-driven
// impact facts; it must match rm_author_impact's stored source so the per-tag
// impactId drill-down anchor stays identical across summary and evidence.
const authorImpactEvidenceSource = "behavior"

// recordAuthorImpactEvidence materializes one paginated evidence fact per
// (tagRef) for an impact-bearing behavior. impactId is derived identically to
// the rm_author_impact summary row so the app can drill from a count to its
// underlying facts. actorId is stored for dedupe only and never surfaced.
func (s *BehaviorService) recordAuthorImpactEvidence(
	ctx context.Context,
	sig rtrec.BehaviorSignal,
	event ports.AuthorImpactEvent,
	occurredAt time.Time,
) error {
	if s.authorImpactEvidence == nil {
		return nil
	}
	authorID := strings.TrimSpace(event.AuthorID)
	if authorID == "" {
		return nil
	}
	tagRefs := ports.NormalizeImpactTags(event.IntersectionTagRefs)
	if len(tagRefs) == 0 {
		tagRefs = []string{""}
	}
	occur := occurredAt
	if !sig.Timestamp.IsZero() {
		occur = sig.Timestamp
	}
	for _, tagRef := range tagRefs {
		impactID := ports.StableImpactID(
			authorID,
			event.HelpType,
			event.Action,
			event.IntersectionDimension,
			tagRef,
			authorImpactEvidenceSource,
		)
		if err := s.authorImpactEvidence.Record(ctx, ports.AuthorImpactEvidenceRecord{
			AuthorID:              authorID,
			ImpactID:              impactID,
			SourceEventID:         evidenceSourceEventID(sig, tagRef),
			ActorID:               strings.TrimSpace(sig.UserID),
			ContentID:             strings.TrimSpace(sig.ContentID),
			ContentType:           strings.TrimSpace(sig.ContentType),
			HelpType:              event.HelpType,
			Action:                event.Action,
			IntersectionDimension: event.IntersectionDimension,
			TagRef:                tagRef,
			Source:                authorImpactEvidenceSource,
			OccurredAt:            occur,
		}); err != nil {
			return err
		}
	}
	return nil
}

// evidenceSourceEventID makes the idempotency key unique per (clientEventId,
// tagRef). clientEventId is validated before this function is reached.
func evidenceSourceEventID(sig rtrec.BehaviorSignal, tagRef string) string {
	base := strings.TrimSpace(sig.ClientEventID)
	if base == "" {
		return ""
	}
	if strings.TrimSpace(tagRef) == "" {
		return base
	}
	return base + "|" + tagRef
}
