package semantic

import (
	"fmt"
	"reflect"
	"strings"
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

func Present(raw any) bool {
	return raw != nil
}

func Project(raw any) Projection {
	rows := Rows(raw)
	entityRefs := make([]string, 0)
	tagRefs := make([]string, 0)
	entitySeen := map[string]struct{}{}
	tagSeen := map[string]struct{}{}
	invalid := 0

	for _, row := range rows {
		if normalizeStatus(stringValue(row["status"])) != StatusPublished {
			continue
		}
		kind := normalizeKind(stringValue(row["kind"]))
		targetRef := strings.TrimSpace(stringValue(row["targetRef"]))
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

func ValidateSuppliedRefs(raw any, entityRefs, tagRefs []string) error {
	if err := RejectCandidateRefs(entityRefs, tagRefs); err != nil {
		return err
	}
	if !Present(raw) {
		return nil
	}
	projected := Project(raw)
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

func ApplyGovernanceEvent(raw any, event GovernanceEvent) (any, int, error) {
	if err := ValidateGovernanceEvent(event); err != nil {
		return raw, 0, err
	}
	rows := Rows(raw)
	updated := 0
	for _, row := range rows {
		if strings.TrimSpace(stringValue(row["candidateId"])) != strings.TrimSpace(event.CandidateID) {
			continue
		}
		if kind := normalizeKind(event.Kind); kind != "" {
			row["kind"] = kind
		}
		row["status"] = normalizeStatus(event.Status)
		if normalizeStatus(event.Status) == StatusPublished {
			row["targetRef"] = strings.TrimSpace(event.TargetRef)
		}
		updated++
	}
	return rowsAsAny(rows), updated, nil
}

func Rows(raw any) []map[string]any {
	if raw == nil {
		return nil
	}
	value := reflect.ValueOf(raw)
	if value.Kind() != reflect.Slice && value.Kind() != reflect.Array {
		return nil
	}
	rows := make([]map[string]any, 0, value.Len())
	for i := 0; i < value.Len(); i++ {
		item := value.Index(i)
		if item.Kind() == reflect.Interface {
			if item.IsNil() {
				continue
			}
			item = item.Elem()
		}
		if !item.IsValid() || item.Kind() != reflect.Map {
			continue
		}
		row := map[string]any{}
		iter := item.MapRange()
		for iter.Next() {
			key := iter.Key()
			if key.Kind() != reflect.String {
				continue
			}
			row[key.String()] = iter.Value().Interface()
		}
		rows = append(rows, row)
	}
	return rows
}

func rowsAsAny(rows []map[string]any) []any {
	out := make([]any, 0, len(rows))
	for _, row := range rows {
		out = append(out, row)
	}
	return out
}

func normalizeKind(kind string) string {
	return strings.ToLower(strings.TrimSpace(kind))
}

func normalizeStatus(status string) string {
	return strings.ToLower(strings.TrimSpace(status))
}

func stringValue(value any) string {
	text, _ := value.(string)
	return text
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
	return reflect.DeepEqual(leftSet, rightSet)
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
