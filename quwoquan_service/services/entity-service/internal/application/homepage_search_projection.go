package application

import (
	"context"
	"strings"

	rtsearch "quwoquan_service/runtime/search"
)

// ProjectorEvent is the entity-domain search-index lifecycle event. entity-service
// has no Mongo change-stream / outbox event bus, so the homepage service emits this
// directly after a mutation that changes the searchable surface. The full homepage
// snapshot is carried in the event (write-time reconcile is synchronous and in
// process), so the projector never needs to read state back.
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

// ListHomepagesForIndex returns cloned snapshots of every homepage for cold-start
// backfill. Eligibility filtering (published) is applied by the backfill caller so
// the reader stays a plain enumeration.
func (s *HomepageService) ListHomepagesForIndex(_ context.Context) []Homepage {
	s.mu.RLock()
	defer s.mu.RUnlock()
	out := make([]Homepage, 0, len(s.homepages))
	for _, homepage := range s.homepages {
		out = append(out, cloneHomepage(homepage))
	}
	return out
}

// emitSearchIndex forwards a lifecycle event to the optional search-index
// projector. It must be called outside s.mu so a (bounded) ES round trip never
// holds the homepage write lock; the projector itself swallows ES failures.
func (s *HomepageService) emitSearchIndex(ctx context.Context, event ProjectorEvent) {
	if s.searchProjector == nil {
		return
	}
	_ = s.searchProjector.Project(ctx, event)
}
