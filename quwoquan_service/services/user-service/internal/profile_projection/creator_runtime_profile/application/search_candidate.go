package application

import (
	"context"
	"fmt"
	rt "quwoquan_service/runtime/search"
	"quwoquan_service/services/user-service/internal/profile_projection/creator_runtime_profile/domain/model"
	"sort"
	"strings"
)

type SearchCandidateStore interface {
	ReadSearchCandidate(context.Context, model.ReleaseIdentity) (model.CreatorReleaseCandidateState, []model.CreatorReleaseProjection, bool, error)
}
type SearchCandidateReader struct{ store SearchCandidateStore }

func NewSearchCandidateReader(store SearchCandidateStore) *SearchCandidateReader {
	return &SearchCandidateReader{store}
}
func (r *SearchCandidateReader) Read(ctx context.Context, b rt.ReleaseCandidateBinding) (*rt.CreatorSearchCandidateSnapshot, error) {
	if err := b.Validate(); err != nil {
		return nil, err
	}
	if r.store == nil {
		return nil, fmt.Errorf("Creator candidate store unavailable")
	}
	state, rows, found, err := r.store.ReadSearchCandidate(ctx, model.ReleaseIdentity{Environment: b.Environment, SourceOwner: b.SourceOwner, ReleaseID: b.ReleaseID, ManifestDigest: b.ManifestDigest})
	if err != nil || !found {
		return nil, err
	}
	snapshot := &rt.CreatorSearchCandidateSnapshot{Release: b, SourceClosureDigest: state.ClosureDigest, Profiles: []rt.CreatorSearchPublicSnapshot{}}
	for _, row := range rows {
		p := row.Profile
		tags := append([]string{}, p.PublicProfileTagRefs...)
		tags = append(tags, p.Roles...)
		tags = append(tags, p.Verticals...)
		sort.Strings(tags)
		v := rt.CreatorSearchPublicSnapshot{ObjectType: rt.ObjectTypeUserProfile, ObjectID: p.PersonaID, CreatorID: p.CreatorID, PersonaID: p.PersonaID, AuthorID: row.AuthorID, UserHandle: p.Handle, DisplayName: p.DisplayName, Bio: optionalCreatorText(p.Bio), IdentityTags: tags, PostCount: int64(len(p.Works)), SourceVersion: row.ProjectionVersion, ProfileDigest: row.ProfileDigest, UpdatedAt: p.UpdatedAt.UTC().Format("2006-01-02T15:04:05.999999999Z07:00")}
		if strings.TrimSpace(p.AvatarAssetID) != "" {
			if strings.TrimSpace(p.AvatarPublicSliceKey) == "" || strings.TrimSpace(p.AvatarURL) == "" {
				return nil, fmt.Errorf("%w: avatar lacks verified public binding", rt.ErrCreatorSourceInvalid)
			}
			mode := "public"
			v.AvatarURL = &p.AvatarURL
			v.AvatarAssetID = &p.AvatarAssetID
			v.AvatarAccessMode = &mode
		}
		snapshot.Profiles = append(snapshot.Profiles, v)
	}
	if err = snapshot.Seal(); err != nil {
		return nil, err
	}
	if err = snapshot.Validate(); err != nil {
		return nil, fmt.Errorf("%w: %v", rt.ErrCreatorSourceInvalid, err)
	}
	return snapshot, nil
}
func optionalCreatorText(s string) *string {
	if strings.TrimSpace(s) == "" {
		return nil
	}
	return &s
}
