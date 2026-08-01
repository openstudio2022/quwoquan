package semantic

import (
	"fmt"
	"strings"

	postmodel "quwoquan_service/services/content-service/generated/content/post/contract/model"
)

const (
	KindEntity = "entity"
	KindTag    = "tag"

	StatusPublished     = "published"
	StatusPendingReview = "pending_review"
	StatusRejected      = "rejected"
	StatusOffline       = "offline"
)

type Projection struct {
	EntityRefs            []string
	TagRefs               []string
	InvalidPublishedCount int
}

type GovernanceEvent struct {
	CandidateID string `json:"candidateId"`
	Kind        string `json:"kind"`
	Status      string `json:"status"`
	TargetRef   string `json:"targetRef"`
}

func Present(mentions []postmodel.PostSemanticMention) bool {
	return len(mentions) > 0
}

func Project(mentions []postmodel.PostSemanticMention) Projection {
	entityRefs := make([]string, 0)
	tagRefs := make([]string, 0)
	entitySeen := map[string]struct{}{}
	tagSeen := map[string]struct{}{}
	invalid := 0

	for _, mention := range mentions {
		if normalizeStatus(mention.Status) != StatusPublished {
			continue
		}
		kind := normalizeKind(mention.Kind)
		targetRef := strings.TrimSpace(mention.TargetRef)
		if !ValidTargetRef(kind, targetRef) {
			invalid++
			continue
		}
		switch kind {
		case KindEntity:
			if _, ok := entitySeen[targetRef]; ok {
				continue
			}
			entitySeen[targetRef] = struct{}{}
			entityRefs = append(entityRefs, targetRef)
		case KindTag:
			if _, ok := tagSeen[targetRef]; ok {
				continue
			}
			tagSeen[targetRef] = struct{}{}
			tagRefs = append(tagRefs, targetRef)
		}
	}

	return Projection{
		EntityRefs:            entityRefs,
		TagRefs:               tagRefs,
		InvalidPublishedCount: invalid,
	}
}

func ValidateSuppliedRefs(mentions []postmodel.PostSemanticMention, entityRefs, tagRefs []string) error {
	if err := RejectCandidateRefs(entityRefs, tagRefs); err != nil {
		return err
	}
	if !Present(mentions) {
		return nil
	}
	projected := Project(mentions)
	if projected.InvalidPublishedCount > 0 {
		return fmt.Errorf("semanticMentions contains %d published mention(s) with invalid targetRef", projected.InvalidPublishedCount)
	}
	if len(entityRefs) > 0 && !sameStrings(entityRefs, projected.EntityRefs) {
		return fmt.Errorf("entityRefs is a read-only projection of published semanticMentions")
	}
	if len(tagRefs) > 0 && !sameStrings(tagRefs, projected.TagRefs) {
		return fmt.Errorf("tagRefs is a read-only projection of published semanticMentions")
	}
	return nil
}

func RejectCandidateRefs(refGroups ...[]string) error {
	for _, refs := range refGroups {
		for _, ref := range refs {
			if CandidateRef(ref) {
				return fmt.Errorf("candidate ref %q cannot be used as an active reference", ref)
			}
		}
	}
	return nil
}

func ValidTargetRef(kind, targetRef string) bool {
	ref := strings.TrimSpace(targetRef)
	if ref == "" || CandidateRef(ref) || strings.ContainsAny(ref, "\r\n\t") {
		return false
	}
	switch normalizeKind(kind) {
	case KindEntity:
		if strings.HasPrefix(ref, "entity:") {
			return len(nonEmptyParts(strings.Split(ref, ":"))) >= 3
		}
		if strings.HasPrefix(ref, "/entity/") || strings.HasPrefix(ref, "entity/") {
			return len(nonEmptyParts(strings.Split(strings.TrimPrefix(ref, "/"), "/"))) >= 4
		}
		return strings.HasPrefix(ref, "homepage_")
	case KindTag:
		switch {
		case strings.HasPrefix(ref, "tag:"):
			return len(nonEmptyParts(strings.Split(ref, ":"))) >= 2
		case strings.HasPrefix(ref, "/tag/"):
			return len(nonEmptyParts(strings.Split(strings.TrimPrefix(ref, "/tag/"), "/"))) >= 2
		case strings.HasPrefix(ref, "tag/"):
			return len(nonEmptyParts(strings.Split(strings.TrimPrefix(ref, "tag/"), "/"))) >= 2
		default:
			return len(nonEmptyParts(strings.Split(ref, "/"))) >= 2
		}
	default:
		return false
	}
}

func CandidateRef(ref string) bool {
	normalized := strings.ToLower(strings.TrimSpace(ref))
	return strings.Contains(normalized, "candidate")
}

func ValidateGovernanceEvent(event GovernanceEvent) error {
	event.CandidateID = strings.TrimSpace(event.CandidateID)
	if event.CandidateID == "" {
		return fmt.Errorf("candidateId is required")
	}
	status := normalizeStatus(event.Status)
	switch status {
	case StatusPublished:
		if !ValidTargetRef(event.Kind, event.TargetRef) {
			return fmt.Errorf("published governance event requires a valid targetRef")
		}
	case StatusPendingReview, StatusRejected, StatusOffline:
	default:
		return fmt.Errorf("unsupported semantic mention status %q", event.Status)
	}
	return nil
}

func ApplyGovernanceEvent(
	mentions []postmodel.PostSemanticMention,
	event GovernanceEvent,
) ([]postmodel.PostSemanticMention, int, error) {
	if err := ValidateGovernanceEvent(event); err != nil {
		return mentions, 0, err
	}
	updatedMentions := append([]postmodel.PostSemanticMention(nil), mentions...)
	updated := 0
	for index := range updatedMentions {
		mention := &updatedMentions[index]
		if strings.TrimSpace(mention.CandidateId) != strings.TrimSpace(event.CandidateID) {
			continue
		}
		if kind := normalizeKind(event.Kind); kind != "" {
			mention.Kind = kind
		}
		mention.Status = normalizeStatus(event.Status)
		if normalizeStatus(event.Status) == StatusPublished {
			mention.TargetRef = strings.TrimSpace(event.TargetRef)
		}
		updated++
	}
	return updatedMentions, updated, nil
}

func Rows(mentions []postmodel.PostSemanticMention) []postmodel.PostSemanticMention {
	return mentions
}

func normalizeKind(kind string) string {
	return strings.ToLower(strings.TrimSpace(kind))
}

func normalizeStatus(status string) string {
	return strings.ToLower(strings.TrimSpace(status))
}

func nonEmptyParts(parts []string) []string {
	out := make([]string, 0, len(parts))
	for _, part := range parts {
		if strings.TrimSpace(part) != "" {
			out = append(out, part)
		}
	}
	return out
}

func sameStrings(left, right []string) bool {
	leftSet := normalizedSet(left)
	rightSet := normalizedSet(right)
	if len(leftSet) != len(rightSet) {
		return false
	}
	for item := range leftSet {
		if _, found := rightSet[item]; !found {
			return false
		}
	}
	return true
}

func normalizedSet(items []string) map[string]struct{} {
	out := make(map[string]struct{}, len(items))
	for _, item := range items {
		if normalized := strings.TrimSpace(item); normalized != "" {
			out[normalized] = struct{}{}
		}
	}
	return out
}
