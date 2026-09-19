// spec_ref: specs/feature-tree/user-identity-profile-relationship/persona-follow-graph/follow-relationship/spec.md#gwt-005
package local_contract

import (
	"context"
	"errors"
	"testing"
	"time"

	usermodel "quwoquan_service/services/user-service/internal/account/user_account/domain/user/model"
	userrepo "quwoquan_service/services/user-service/internal/account/user_account/domain/user/ports"
	relationshipapp "quwoquan_service/services/user-service/internal/relationship/persona_relationship/application"
)

// resolverPersonaReader 只回答目标解析需要的 Persona 事实，不携带私有字段。
type resolverPersonaReader struct {
	byPersonaID map[string]*usermodel.Persona
	byHandle    map[string]*usermodel.Persona
}

func (reader *resolverPersonaReader) FindByID(
	_ context.Context, _ string,
) (*usermodel.Persona, error) {
	return nil, errors.New("FindByID is not part of relationship target resolution")
}

func (reader *resolverPersonaReader) FindByUserID(
	_ context.Context, _ string,
) ([]usermodel.Persona, error) {
	return nil, errors.New("FindByUserID is not part of relationship target resolution")
}

func (reader *resolverPersonaReader) FindActiveByUserID(
	_ context.Context, _ string,
) (*usermodel.Persona, error) {
	return nil, errors.New("FindActiveByUserID is not part of relationship target resolution")
}

func (reader *resolverPersonaReader) FindByUserHandle(
	_ context.Context, handle string,
) (*usermodel.Persona, error) {
	return reader.byHandle[handle], nil
}

func (reader *resolverPersonaReader) FindByPersonaID(
	_ context.Context, personaID string,
) (*usermodel.Persona, error) {
	return reader.byPersonaID[personaID], nil
}

// resolverCreatorReader 按 exact fence 返回已发布 Creator 公开身份。
type resolverCreatorReader struct {
	byIdentity map[string]*userrepo.CreatorRuntimeProfileView
	seenFences []userrepo.ContentReleaseFence
}

func (reader *resolverCreatorReader) FindByExactContentFence(
	_ context.Context,
	fence userrepo.ContentReleaseFence,
	identity string,
) (*userrepo.CreatorRuntimeProfileView, bool, error) {
	reader.seenFences = append(reader.seenFences, fence)
	creator, found := reader.byIdentity[identity]
	return creator, found, nil
}

func (reader *resolverCreatorReader) ListWorksByExactContentFence(
	_ context.Context,
	_ userrepo.ContentReleaseFence,
	_ string,
) ([]userrepo.CreatorWorkView, bool, error) {
	return nil, false, errors.New("works are not part of relationship target resolution")
}

type resolverFenceReader struct {
	fence userrepo.ContentReleaseFence
	found bool
}

func (reader resolverFenceReader) ActiveContentReleaseFence(
	_ context.Context,
) (userrepo.ContentReleaseFence, bool, error) {
	return reader.fence, reader.found, nil
}

func livePersona(personaID, handle string) *usermodel.Persona {
	return &usermodel.Persona{
		PersonaID:  personaID,
		UserHandle: handle,
		Status:     "active",
		UpdatedAt:  time.Now().UTC(),
	}
}

func TestRelationshipTargetResolverKeepsOneCanonicalIdentityPerSubject(t *testing.T) {
	t.Parallel()

	const (
		livePersonaID    = "us_01_0a1b_persona000000000000000000"
		liveHandle       = "qwlivepersona"
		creatorPersonaID = "us_01_0a1b_creator000000000000000000"
		creatorHandle    = "qwcreator"
		retiredPersonaID = "us_01_0a1b_retired000000000000000000"
	)
	fence := userrepo.ContentReleaseFence{
		Environment:    "alpha",
		SourceOwner:    "qwq_data",
		ReleaseID:      "release-1",
		ManifestDigest: "sha256:release-1",
	}
	personas := &resolverPersonaReader{
		byPersonaID: map[string]*usermodel.Persona{
			livePersonaID: livePersona(livePersonaID, liveHandle),
			retiredPersonaID: {
				PersonaID: retiredPersonaID,
				Status:    "retired",
			},
		},
		byHandle: map[string]*usermodel.Persona{
			liveHandle: livePersona(livePersonaID, liveHandle),
		},
	}
	creators := &resolverCreatorReader{
		byIdentity: map[string]*userrepo.CreatorRuntimeProfileView{
			creatorPersonaID: {CreatorID: "creator-1", PersonaID: creatorPersonaID, Handle: creatorHandle},
			creatorHandle:    {CreatorID: "creator-1", PersonaID: creatorPersonaID, Handle: creatorHandle},
		},
	}
	resolver := relationshipapp.NewRelationshipTargetResolver(
		personas,
		creators,
		resolverFenceReader{fence: fence, found: true},
	)
	ctx := context.Background()

	t.Run("live persona resolves by id and by handle to the same identity", func(t *testing.T) {
		for _, identity := range []string{livePersonaID, liveHandle} {
			resolved, err := resolver.ResolveTarget(ctx, identity)
			if err != nil {
				t.Fatalf("ResolveTarget(%q) error = %v", identity, err)
			}
			if resolved.PersonaID != livePersonaID {
				t.Fatalf("ResolveTarget(%q) = %q, want canonical %q", identity, resolved.PersonaID, livePersonaID)
			}
			if resolved.Kind != relationshipapp.TargetKindPersona {
				t.Fatalf("ResolveTarget(%q) kind = %q", identity, resolved.Kind)
			}
		}
	})

	t.Run("published creator resolves to its canonical persona identity", func(t *testing.T) {
		for _, identity := range []string{creatorPersonaID, creatorHandle} {
			resolved, err := resolver.ResolveTarget(ctx, identity)
			if err != nil {
				t.Fatalf("ResolveTarget(%q) error = %v", identity, err)
			}
			if resolved.PersonaID != creatorPersonaID {
				t.Fatalf("ResolveTarget(%q) = %q, want %q", identity, resolved.PersonaID, creatorPersonaID)
			}
			if resolved.Kind != relationshipapp.TargetKindCreator {
				t.Fatalf("ResolveTarget(%q) kind = %q, want creator", identity, resolved.Kind)
			}
		}
		if len(creators.seenFences) == 0 {
			t.Fatal("creator read must go through the exact Content fence")
		}
		for _, seen := range creators.seenFences {
			if seen != fence {
				t.Fatalf("creator read used fence %+v, want %+v", seen, fence)
			}
		}
	})

	t.Run("creator can never be the command actor", func(t *testing.T) {
		if _, err := resolver.ResolveActor(ctx, creatorPersonaID); err == nil {
			t.Fatal("ResolveActor(creator) error = nil, want actor forbidden")
		}
		actor, err := resolver.ResolveActor(ctx, livePersonaID)
		if err != nil || actor != livePersonaID {
			t.Fatalf("ResolveActor(live persona) = %q err = %v", actor, err)
		}
		if _, err := resolver.ResolveActor(ctx, liveHandle); err == nil {
			t.Fatal("ResolveActor(handle) error = nil, want immutable id requirement")
		}
	})

	t.Run("unresolved retired and empty identities never produce a target", func(t *testing.T) {
		for name, identity := range map[string]string{
			"empty":      "   ",
			"unknown":    "us_01_0a1b_missing000000000000000000",
			"retired":    retiredPersonaID,
			"stale name": "no-such-handle",
		} {
			if _, err := resolver.ResolveTarget(ctx, identity); err == nil {
				t.Fatalf("ResolveTarget(%s) error = nil, want canonical failure", name)
			}
		}
	})
}

func TestRelationshipTargetResolverRejectsCrossTypeIdentityCollision(t *testing.T) {
	t.Parallel()

	const (
		sharedIdentity   = "us_01_0a1b_shared0000000000000000000"
		creatorPersonaID = "us_01_0a1b_creator000000000000000000"
	)
	personas := &resolverPersonaReader{
		byPersonaID: map[string]*usermodel.Persona{
			sharedIdentity: livePersona(sharedIdentity, "qwshared"),
		},
		byHandle: map[string]*usermodel.Persona{},
	}
	creators := &resolverCreatorReader{
		byIdentity: map[string]*userrepo.CreatorRuntimeProfileView{
			// 同一字节同时命中 Persona 与另一个主体的 Creator 公开身份。
			sharedIdentity: {CreatorID: "creator-1", PersonaID: creatorPersonaID},
		},
	}
	resolver := relationshipapp.NewRelationshipTargetResolver(
		personas,
		creators,
		resolverFenceReader{found: true},
	)

	if _, err := resolver.ResolveTarget(context.Background(), sharedIdentity); err == nil {
		t.Fatal("cross-type identity collision must be rejected, not silently preferred")
	}

	// 同一主体的两种视图（Creator 指回同一 persona）仍然可解析为该 persona。
	creators.byIdentity[sharedIdentity] = &userrepo.CreatorRuntimeProfileView{
		CreatorID: "creator-1",
		PersonaID: sharedIdentity,
	}
	resolved, err := resolver.ResolveTarget(context.Background(), sharedIdentity)
	if err != nil || resolved.PersonaID != sharedIdentity {
		t.Fatalf("same-subject dual view resolve = %+v err = %v", resolved, err)
	}
	if resolved.Kind != relationshipapp.TargetKindPersona {
		t.Fatalf("live persona view must win kind, got %q", resolved.Kind)
	}
}

func TestRelationshipTargetResolverBlocksPublishedCreatorWithoutCanonicalIdentity(t *testing.T) {
	t.Parallel()

	const creatorHandle = "qwcreatornoidentity"
	creators := &resolverCreatorReader{
		byIdentity: map[string]*userrepo.CreatorRuntimeProfileView{
			creatorHandle: {CreatorID: "creator-2", PersonaID: "  "},
		},
	}
	resolver := relationshipapp.NewRelationshipTargetResolver(
		&resolverPersonaReader{
			byPersonaID: map[string]*usermodel.Persona{},
			byHandle:    map[string]*usermodel.Persona{},
		},
		creators,
		resolverFenceReader{found: true},
	)

	if _, err := resolver.ResolveTarget(context.Background(), creatorHandle); err == nil {
		t.Fatal("published Creator without canonical persona identity must block the entry point")
	}
}

func TestRelationshipTargetResolverWithoutActiveFenceHasNoCreatorTarget(t *testing.T) {
	t.Parallel()

	const creatorHandle = "qwcreatorunfenced"
	resolver := relationshipapp.NewRelationshipTargetResolver(
		&resolverPersonaReader{
			byPersonaID: map[string]*usermodel.Persona{},
			byHandle:    map[string]*usermodel.Persona{},
		},
		&resolverCreatorReader{
			byIdentity: map[string]*userrepo.CreatorRuntimeProfileView{
				creatorHandle: {CreatorID: "creator-3", PersonaID: "us_01_0a1b_creator000000000000000000"},
			},
		},
		resolverFenceReader{found: false},
	)

	if _, err := resolver.ResolveTarget(context.Background(), creatorHandle); err == nil {
		t.Fatal("no active fence must fail closed instead of exposing a release Creator")
	}
}
