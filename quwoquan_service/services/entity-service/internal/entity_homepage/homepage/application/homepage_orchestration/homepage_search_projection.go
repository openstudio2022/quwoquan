package application

import (
	"context"
	"strings"

	rtsearch "quwoquan_service/runtime/search"
)

// ProjectorEvent 是 commit 后的同进程 best-effort 搜索投影事件；Homepage 事实源是
// 同事务写入的 homepage_outbox，本事件只缩短可见延迟，不能替代 outbox 重放。
type ProjectorEvent struct {
	Type       string
	HomepageID string
	// Homepage is the post-mutation snapshot. nil means "removed" (delete only).
	Homepage *Homepage
}

const (
	// ProjectorEventHomepageUpserted reconciles a homepage against its current
	// eligibility (upsert when published, delete otherwise).
	ProjectorEventHomepageUpserted = "HomepageUpserted"
	// ProjectorEventHomepageRemoved removes a homepage from the index (offline).
	ProjectorEventHomepageRemoved = "HomepageRemoved"
)

// Projector is the write-time search-index projector contract implemented by the
// infrastructure searchindex package. It is optional: when ES is disabled the
// homepage service holds a nil projector and every emit is a no-op, so the primary
// write path is unaffected.
type Projector interface {
	Project(ctx context.Context, event ProjectorEvent) error
}

// HomepageSearchEligible mirrors SearchHomepages' default visibility (published
// homepages are the discoverable set). The ES index must contain exactly the same
// set the native search surface exposes.
func HomepageSearchEligible(homepage Homepage) bool {
	return strings.EqualFold(strings.TrimSpace(homepage.Status), "published")
}

// ProjectHomepageToSearchDocument projects a homepage into the unified search
// Document (objectType entity.homepage, target derived as "entity"). It is the
// single source of truth for homepage→Document mapping, shared by the native
// SearchHomepages surface and the ES search-index projector/backfill so the two
// never diverge.
func ProjectHomepageToSearchDocument(homepage Homepage) rtsearch.Document {
	// entityId / entityName are anchor fields the ES indexer flattens for reverse
	// lookup (runtime/search/es.anchorFieldKeys). placeName is the cross-object
	// location dimension (R-S05e): it is indexed + round-tripped so 附近/地点检索
	// spans all object types uniformly. address stays a native-matcher-only field
	// (dropped by DocumentToIndex). Both consumers share this one function so the
	// searchable surface never diverges.
	fields := map[string]string{
		"entityId":   homepage.CanonicalEntityID,
		"entityName": homepage.Title,
	}
	// placeName = city: the administrative place the entity sits in. The entity
	// itself IS the place, so no synthetic placeId is set (its CanonicalEntityID
	// is already the place's canonical identity via entityId/Entities).
	if v := strings.TrimSpace(homepage.City); v != "" {
		fields["placeName"] = v
	}
	if v := strings.TrimSpace(homepage.Address); v != "" {
		fields["address"] = v
	}
	// A user suggestion opened from a first-party location.place carries its
	// validated immutable place id in the internal lookup aliases. Once the
	// candidate is published this anchor lets canonical /search(ids:[placeId])
	// resolve the promoted homepage without resurrecting a duplicate place doc.
	if placeID := sourcePlaceAlias(homepage.LookupAliases); placeID != "" {
		fields["placeId"] = placeID
	}
	doc := rtsearch.Document{
		ObjectType:   rtsearch.ObjectTypeEntityHomepage,
		ObjectID:     homepage.ID,
		Title:        homepage.Title,
		Summary:      homepage.Subtitle,
		SourceDomain: "entity",
		ContentType:  homepage.HomepageType,
		Visibility:   "public",
		BadgeLabel:   "主页",
		Tags:         homepage.CategoryTags,
		Entities:     []string{homepage.CanonicalEntityID},
		Popularity:   float64(homepage.RatingCount),
		Freshness:    homepage.UpdatedAt,
		Fields:       fields,
	}
	// Geo comes straight from the real Homepage.location (NULLABLE GeoPoint); never
	// fabricated. When present it drives the ES geo_point + native 附近 radius.
	if homepage.Location != nil {
		doc.Geo = &rtsearch.GeoPoint{Lat: homepage.Location.Latitude, Lng: homepage.Location.Longitude}
	}
	return doc
}

func sourcePlaceAlias(aliases []string) string {
	const prefix = "place_"
	for _, raw := range aliases {
		id := strings.TrimSpace(raw)
		if len(id) != len(prefix)+16 || !strings.HasPrefix(id, prefix) {
			continue
		}
		valid := true
		for _, char := range id[len(prefix):] {
			if !((char >= '0' && char <= '9') || (char >= 'a' && char <= 'f')) {
				valid = false
				break
			}
		}
		if valid {
			return id
		}
	}
	return ""
}

// ListHomepagesForIndex 直接 cursor 扫描权威 homepages 集合。
func (s *HomepageService) ListHomepagesForIndex(ctx context.Context) []Homepage {
	out := []Homepage{}
	cursor := ""
	for {
		items, next, err := s.queries.Scan(ctx, cursor, 500)
		if err != nil {
			return out
		}
		out = append(out, items...)
		if next == "" {
			return out
		}
		cursor = next
	}
}

func (s *HomepageService) ScanHomepagesForIndex(
	ctx context.Context,
	cursor string,
	limit int,
) ([]Homepage, string, error) {
	return s.queries.Scan(ctx, cursor, limit)
}
