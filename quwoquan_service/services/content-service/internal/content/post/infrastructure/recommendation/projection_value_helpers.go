package recommendation

import (
	"strings"
	"time"

	rtrec "quwoquan_service/runtime/recommendation"
)

func StrVal(values map[string]any, key string) string {
	value, _ := values[key].(string)
	return value
}

func AnySlice(values map[string]any, key string) []string {
	raw, ok := values[key].([]any)
	if !ok {
		items, _ := values[key].([]string)
		return items
	}
	items := make([]string, 0, len(raw))
	for _, value := range raw {
		if item, ok := value.(string); ok {
			items = append(items, item)
		}
	}
	return items
}

func normalizeVisibility(value string) string {
	normalized := strings.TrimSpace(strings.ToLower(value))
	if normalized == "" {
		return "public"
	}
	return normalized
}

// discoveryFeedDoc remains only as the decoder boundary for Content's remaining
// intersection presentation source. Candidate ranking no longer consumes it;
// the remaining read path will be replaced by a typed Recommendation port.
type discoveryFeedDoc struct {
	PostID                      string    `bson:"postId"`
	ContentType                 string    `bson:"contentType"`
	AuthorID                    string    `bson:"authorId"`
	Title                       string    `bson:"title"`
	Tags                        []string  `bson:"tagRefs"`
	EntityRefs                  []string  `bson:"entityRefs"`
	PublishedAt                 time.Time `bson:"publishedAt"`
	RecScore                    float64   `bson:"recScore"`
	QualityScore                float64   `bson:"qualityScore"`
	ContentVertical             string    `bson:"contentVertical"`
	SupplySource                string    `bson:"supplySource"`
	SourceOwner                 string    `bson:"sourceOwner"`
	ReleaseID                   string    `bson:"releaseId"`
	ManifestDigest              string    `bson:"manifestDigest"`
	LifecycleStatus             string    `bson:"lifecycleStatus"`
	IntersectionFactStrength    float64   `bson:"intersectionFactStrength"`
	IntersectionFreshness       float64   `bson:"intersectionFreshness"`
	AffinityIntersectionScore   float64   `bson:"affinityIntersectionScore"`
	IntersectionSourceRefTop    string    `bson:"intersectionSourceRefTop"`
	IntersectionConfidenceLabel string    `bson:"intersectionConfidenceLabel"`
	IntersectionClass           string    `bson:"intersectionClass"`
}

func candidateFromDiscoveryDoc(doc discoveryFeedDoc, recallPath string) rtrec.ContentCandidate {
	qualityScore := doc.QualityScore
	if qualityScore <= 0 {
		qualityScore = doc.RecScore
	}
	return rtrec.ContentCandidate{
		ContentID:                   doc.PostID,
		ContentType:                 doc.ContentType,
		AuthorID:                    doc.AuthorID,
		Title:                       doc.Title,
		Tags:                        doc.Tags,
		EntityRefs:                  doc.EntityRefs,
		PublishedAt:                 doc.PublishedAt,
		RecallPath:                  recallPath,
		QualityScore:                qualityScore,
		ContentVertical:             doc.ContentVertical,
		SupplySource:                doc.SupplySource,
		SourceOwner:                 doc.SourceOwner,
		ReleaseID:                   doc.ReleaseID,
		ManifestDigest:              doc.ManifestDigest,
		LifecycleStatus:             doc.LifecycleStatus,
		IntersectionFactStrength:    doc.IntersectionFactStrength,
		IntersectionFreshness:       doc.IntersectionFreshness,
		AffinityIntersectionScore:   doc.AffinityIntersectionScore,
		IntersectionSourceRefTop:    doc.IntersectionSourceRefTop,
		IntersectionConfidenceLabel: doc.IntersectionConfidenceLabel,
		IntersectionClass:           doc.IntersectionClass,
	}
}
