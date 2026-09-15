package persistence

import (
	"context"
	"fmt"
	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo/options"
	rt "quwoquan_service/runtime/search"
	model "quwoquan_service/services/entity-service/internal/entity_homepage/homepage/domain/model"
	ports "quwoquan_service/services/entity-service/internal/entity_homepage/homepage/domain/ports"
	"time"
)

func (s *MongoHomepageStore) ReadHomepageCandidate(ctx context.Context, b rt.ReleaseCandidateBinding) (rt.ReleaseHomepageCandidateSnapshot, error) {
	out := rt.ReleaseHomepageCandidateSnapshot{Release: b, Homepages: []rt.ReleaseHomepagePublicSnapshot{}}
	identity := ports.ReleaseIdentity{Environment: b.Environment, SourceOwner: b.SourceOwner, ReleaseID: b.ReleaseID, ManifestDigest: b.ManifestDigest}
	state, found, err := s.ReadVerifiedReleaseCandidate(ctx, identity)
	if err != nil {
		return out, err
	}
	if !found || state.ExpectedCount > 1000 {
		return out, fmt.Errorf("Homepage candidate not ready")
	}
	out.SourceClosureDigest = state.ClosureDigest
	out.EntityRefMappingDigest = state.EntityRefMappingDigest
	cursor, err := s.releaseProjections.Find(ctx, releaseIdentityFilter(identity), options.Find().SetSort(bson.D{{Key: "homepageId", Value: 1}}).SetLimit(1001))
	if err != nil {
		return out, err
	}
	defer cursor.Close(ctx)
	for cursor.Next(ctx) {
		var row homepageReleaseProjectionDocument
		if err = cursor.Decode(&row); err != nil {
			return out, err
		}
		p := row.projection()
		v := rt.ReleaseHomepagePublicSnapshot{Identity: rt.ReleaseCandidateObjectIdentity{Release: b, ObjectType: "entity.homepage", ObjectID: p.HomepageID, SourceVersion: p.ProjectionVersion, SourceDigest: p.DocumentDigest}, EntityRef: p.EntityRef, CanonicalEntityID: model.CanonicalEntityID(p.HomepageType, p.Title), Title: p.Title, HomepageType: p.HomepageType, IntroductionMarkdown: p.IntroductionMarkdown, TagRefs: append([]string{}, p.CategoryTags...), DeepLink: "quwoquan://homepages/" + p.HomepageID, UpdatedAt: p.VerifiedAt.UTC().Format(time.RFC3339Nano)}
		if p.City != "" {
			v.City = &p.City
		}
		if p.CoverURL != "" {
			v.CoverURL = &p.CoverURL
		}
		if p.Location != nil {
			v.Location = &rt.ReleaseLocation{Latitude: p.Location.Latitude, Longitude: p.Location.Longitude}
		}
		out.Homepages = append(out.Homepages, v)
	}
	if err = cursor.Err(); err != nil {
		return out, err
	}
	if len(out.Homepages) != state.ExpectedCount {
		return out, rt.ErrCreatorSourceInvalid
	}
	if err = out.Seal(); err != nil {
		return out, err
	}
	return out, out.Validate()
}
