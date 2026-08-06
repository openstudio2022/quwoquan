// spec_ref: specs/feature-tree/assistant-run-learning/skill-product-integration-platform/shared-surface-skill-placement/spec.md#gwt-001
// readiness_case: get-skill-surface-placement-api
// readiness_case: put-skill-surface-placement-api
package api_integration

import (
	"bytes"
	"context"
	"crypto/ed25519"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/runtime/operation"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/orchestration"
	activerelease "quwoquan_service/services/assistant-service/internal/assistant/skill_catalog/infrastructure/activerelease"
	resourcebuilder "quwoquan_service/services/assistant-service/internal/assistant/skill_catalog/infrastructure/resource"
	packageapplication "quwoquan_service/services/assistant-service/internal/assistant/skill_package_release/application"
	packagemodel "quwoquan_service/services/assistant-service/internal/assistant/skill_package_release/domain/model"
	placementhttp "quwoquan_service/services/assistant-service/internal/assistant/skill_surface_placement/adapters/inbound/http"
	"quwoquan_service/services/assistant-service/internal/assistant/skill_surface_placement/application"
	"quwoquan_service/services/assistant-service/internal/assistant/skill_surface_placement/domain/model"
	"quwoquan_service/services/assistant-service/internal/assistant/skill_surface_placement/infrastructure/authority"
)

type allowSurfaceAuthority struct{}

func (allowSurfaceAuthority) RequireMember(context.Context, string, string, string) error { return nil }
func (allowSurfaceAuthority) RequireAdmin(context.Context, string, string, string) error  { return nil }

type allowSharedCatalog struct{}

func (allowSharedCatalog) ValidateSharedSkillIDs(context.Context, string, []string) error { return nil }

type placementActiveReleaseResolver struct {
	resolved packageapplication.ResolvedRelease
}

func (resolver placementActiveReleaseResolver) ResolveActive(
	ctx context.Context,
	packageID string,
) (packageapplication.ResolvedRelease, error) {
	if err := ctx.Err(); err != nil {
		return packageapplication.ResolvedRelease{}, err
	}
	if packageID != resolver.resolved.Release.PackageID {
		return packageapplication.ResolvedRelease{}, errors.New("active package not found")
	}
	return resolver.resolved, nil
}

func (resolver placementActiveReleaseResolver) ResolveRelease(
	ctx context.Context,
	packageID string,
	releaseDigest string,
) (packageapplication.ResolvedRelease, error) {
	if err := ctx.Err(); err != nil {
		return packageapplication.ResolvedRelease{}, err
	}
	if packageID != resolver.resolved.Release.PackageID ||
		releaseDigest != resolver.resolved.Release.ReleaseDigest {
		return packageapplication.ResolvedRelease{}, errors.New("immutable release not found")
	}
	return resolver.resolved, nil
}

type placementDelegatedAuthorization struct{}

func (placementDelegatedAuthorization) AuthorizationHeaderForPersona(
	_ context.Context,
	personaID string,
) (string, error) {
	if strings.TrimSpace(personaID) == "" {
		return "", errors.New("persona is required")
	}
	return "Bearer delegated:" + personaID, nil
}

func TestSkillSurfacePlacementPostgresCommitsCASReceiptAndOutboxAtomically(t *testing.T) {
	resetPlacementState(t)
	now := time.Date(2026, 8, 2, 12, 0, 0, 0, time.UTC)
	commands := application.NewCommandFacade(
		placementStore,
		allowSurfaceAuthority{},
		allowSharedCatalog{},
		func() time.Time { return now },
	)
	input := model.PutInput{
		SurfaceKind:      model.SurfaceConversation,
		SurfaceID:        "conversation-a",
		ActorAccountID:   "account-admin",
		ActorPersonaID:   "persona-admin",
		Policy:           model.PolicyAllSharedEligible,
		DisabledSkillIDs: []string{"travel_companion"},
		Status:           model.StatusActive,
		ExpectedRevision: 0,
		IdempotencyKey:   "placement-command-create",
	}
	created, err := commands.Put(context.Background(), input)
	if err != nil || !created.Changed || created.Placement.Revision != 1 {
		t.Fatalf("create result=%+v error=%v", created, err)
	}
	replayed, err := commands.Put(context.Background(), input)
	if err != nil || !replayed.Replayed || replayed.Placement.ID != created.Placement.ID {
		t.Fatalf("replay result=%+v error=%v", replayed, err)
	}
	input.DisabledSkillIDs = []string{}
	if _, err := commands.Put(context.Background(), input); !errors.Is(err, model.ErrIdempotencyConflict) {
		t.Fatalf("idempotency conflict error=%v", err)
	}
	input.IdempotencyKey = "placement-command-update"
	input.ExpectedRevision = 1
	updated, err := commands.Put(context.Background(), input)
	if err != nil || updated.Placement.Revision != 2 || len(updated.Placement.DisabledSkillIDs) != 0 {
		t.Fatalf("update result=%+v error=%v", updated, err)
	}
	queries := application.NewQueryFacade(placementStore, allowSurfaceAuthority{})
	allowed, err := queries.AllowsSkill(
		context.Background(),
		model.SurfaceConversation,
		"conversation-a",
		"travel_companion",
	)
	if err != nil || !allowed {
		t.Fatalf("effective allowed=%v error=%v", allowed, err)
	}
	var placements, receipts, outbox int
	if err := placementPool.QueryRow(context.Background(), `
SELECT
  (SELECT COUNT(*) FROM skill_surface_placements),
  (SELECT COUNT(*) FROM skill_surface_placement_command_receipts),
  (SELECT COUNT(*) FROM skill_surface_placement_outbox)`).Scan(&placements, &receipts, &outbox); err != nil {
		t.Fatal(err)
	}
	if placements != 1 || receipts != 2 || outbox != 2 {
		t.Fatalf("placement/receipt/outbox=%d/%d/%d, want 1/2/2", placements, receipts, outbox)
	}
}

func TestSkillSurfacePlacementHTTPUsesPostgresImmutablePackageAndOwnerServices(
	t *testing.T,
) {
	resetPlacementState(t)
	catalog := productionPlacementCatalogSource(t)
	authorityServer := httptest.NewServer(http.HandlerFunc(
		func(writer http.ResponseWriter, request *http.Request) {
			if request.Header.Get("Authorization") != "Bearer delegated:persona-owner" {
				http.Error(writer, "missing delegated persona", http.StatusUnauthorized)
				return
			}
			writer.Header().Set("Content-Type", "application/json")
			switch request.URL.Path {
			case "/chat/conversations/conversation-http/members":
				if request.URL.Query().Get("query") != "persona-owner" {
					http.Error(writer, "unexpected member query", http.StatusBadRequest)
					return
				}
				_, _ = writer.Write([]byte(`{"items":[{"userId":"persona-owner","userHandle":"owner","displayName":"Owner","avatarUrl":"","role":"owner","memberType":"user","joinedAt":"2026-08-05T00:00:00Z","isCurrentUser":true}]}`))
			case "/circles/circle-http/memberships/self":
				_, _ = writer.Write([]byte(`{"membershipId":"membership-http","version":1,"circleId":"circle-http","personaId":"persona-owner","role":"owner","state":"active","joinedAt":"2026-08-05T00:00:00Z","leftAt":null,"lastActiveAt":null,"contribution":0,"createdAt":"2026-08-05T00:00:00Z","updatedAt":"2026-08-05T00:00:00Z"}`))
			default:
				http.NotFound(writer, request)
			}
		},
	))
	defer authorityServer.Close()
	authorityClient, err := authority.NewClient(
		authorityServer.URL,
		authorityServer.URL,
		authorityServer.Client(),
		authorityServer.Client(),
		placementDelegatedAuthorization{},
	)
	if err != nil {
		t.Fatalf("construct production surface authority client: %v", err)
	}
	mux := http.NewServeMux()
	placementhttp.NewHandler(
		application.NewCommandFacade(
			placementStore,
			authorityClient,
			catalog,
			func() time.Time { return time.Date(2026, 8, 5, 10, 0, 0, 0, time.UTC) },
		),
		application.NewQueryFacade(placementStore, authorityClient),
	).RegisterRoutes(mux)

	for _, target := range []struct {
		kind string
		id   string
	}{
		{kind: model.SurfaceConversation, id: "conversation-http"},
		{kind: model.SurfaceCircle, id: "circle-http"},
	} {
		path := "/assistant/skill-placements/" + target.kind + "/" + target.id
		put := skillSurfacePlacementRequest(
			t,
			mux,
			http.MethodPut,
			path,
			"account-owner",
			"persona-owner",
			"put-"+target.kind+"-http",
			map[string]any{
				"policy":           model.PolicyAllSharedEligible,
				"disabledSkillIds": []string{},
				"status":           model.StatusActive,
				"expectedRevision": 0,
			},
		)
		if put.Code != http.StatusOK {
			t.Fatalf("PUT %s status=%d body=%s", target.kind, put.Code, put.Body.String())
		}
		var receipt model.MutationResult
		if err := json.Unmarshal(put.Body.Bytes(), &receipt); err != nil {
			t.Fatalf("decode PUT %s response: %v", target.kind, err)
		}
		if !receipt.Changed || receipt.Replayed ||
			receipt.Placement.SurfaceKind != target.kind ||
			receipt.Placement.SurfaceID != target.id ||
			receipt.Placement.Revision != 1 {
			t.Fatalf("PUT %s receipt=%+v", target.kind, receipt)
		}

		get := skillSurfacePlacementRequest(
			t,
			mux,
			http.MethodGet,
			path,
			"account-owner",
			"persona-owner",
			"",
			nil,
		)
		if get.Code != http.StatusOK {
			t.Fatalf("GET %s status=%d body=%s", target.kind, get.Code, get.Body.String())
		}
		var loaded model.Placement
		if err := json.Unmarshal(get.Body.Bytes(), &loaded); err != nil {
			t.Fatalf("decode GET %s response: %v", target.kind, err)
		}
		if loaded.ID != receipt.Placement.ID || loaded.SurfaceKind != target.kind ||
			loaded.SurfaceID != target.id {
			t.Fatalf("GET %s placement=%+v", target.kind, loaded)
		}
	}

	var placements, receipts, outbox int
	if err := placementPool.QueryRow(t.Context(), `
SELECT
  (SELECT COUNT(*) FROM skill_surface_placements),
  (SELECT COUNT(*) FROM skill_surface_placement_command_receipts),
  (SELECT COUNT(*) FROM skill_surface_placement_outbox)`).Scan(&placements, &receipts, &outbox); err != nil {
		t.Fatal(err)
	}
	if placements != 2 || receipts != 2 || outbox != 2 {
		t.Fatalf("HTTP placement/receipt/outbox=%d/%d/%d, want 2/2/2", placements, receipts, outbox)
	}
}

func productionPlacementCatalogSource(t *testing.T) *activerelease.CatalogSource {
	t.Helper()
	bundle, err := resourcebuilder.NewSourceBuilder().Compile(t.Context())
	if err != nil {
		t.Fatalf("compile canonical Skill package source: %v", err)
	}
	built, err := resourcebuilder.BuildPackage(bundle, resourcebuilder.PackageBuildOptions{
		PackageID:        activerelease.OfficialPackageID,
		PackageVersion:   "1.0.0",
		BuildID:          "skill-surface-placement-api-integration",
		SourceRepository: "quwoquan",
		SourceRevision:   "assistant-skill-surface-placement-readiness",
		BuiltAt:          time.Date(2026, 8, 5, 8, 0, 0, 0, time.UTC),
		RuntimeCompatibility: packagemodel.RuntimeCompatibility{
			APIVersion:            packagemodel.RuntimeAPIVersion,
			MinimumRuntimeVersion: packagemodel.RuntimeVersion,
			MaximumRuntimeVersion: packagemodel.RuntimeVersion,
		},
		CapabilityGrants: []packagemodel.CapabilityGrant{{
			CapabilityID: "assistant.skill",
			Scope:        "official",
		}},
		SigningKeyID:      "skill-surface-placement-api-integration-key",
		SigningPrivateKey: ed25519.NewKeyFromSeed(make([]byte, ed25519.SeedSize)),
	})
	if err != nil {
		t.Fatalf("build immutable Skill package: %v", err)
	}
	files := make(map[string][]byte, len(built.Files))
	for _, file := range built.Files {
		files[file.RelativePath] = append([]byte(nil), file.Content...)
	}
	assets := make(map[string][]byte, len(built.Release.Assets))
	for _, asset := range built.Release.Assets {
		relative := strings.TrimPrefix(asset.Locator, "skill-package://official/")
		content, found := files[relative]
		if !found {
			t.Fatalf("built immutable asset %q is missing", asset.AssetID)
		}
		assets[asset.AssetID] = content
	}
	return activerelease.NewCatalogSource(
		placementActiveReleaseResolver{resolved: packageapplication.ResolvedRelease{
			Release: built.Release,
			Assets:  assets,
		}},
		activerelease.OfficialPackageID,
		orchestration.ValidateAssistantDomainSkillCatalog,
	)
}

func skillSurfacePlacementRequest(
	t *testing.T,
	handler http.Handler,
	method string,
	path string,
	accountID string,
	personaID string,
	idempotencyKey string,
	body any,
) *httptest.ResponseRecorder {
	t.Helper()
	var payload []byte
	if body != nil {
		var err error
		payload, err = json.Marshal(body)
		if err != nil {
			t.Fatalf("marshal SkillSurfacePlacement request: %v", err)
		}
	}
	request := httptest.NewRequest(method, path, bytes.NewReader(payload))
	if body != nil {
		request.Header.Set("Content-Type", "application/json")
	}
	if idempotencyKey != "" {
		request.Header.Set("Idempotency-Key", idempotencyKey)
	}
	request = request.WithContext(rtauth.WithPrincipal(
		request.Context(),
		rtauth.Principal{Actor: operation.ActorContext{
			AccountID: accountID,
			PersonaID: personaID,
		}},
	))
	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, request)
	return recorder
}
