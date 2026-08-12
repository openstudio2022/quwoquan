package auth

// spec_ref: specs/feature-tree/platform-ops-governance/commercial-readiness-risk-closure/spec.md#sit-002

import (
	"net/http"
	"net/http/httptest"
	"testing"
)

func validMutableTestLiveOperationIdentity(environment string) MutableTestLiveOperationIdentity {
	return MutableTestLiveOperationIdentity{
		Schema:               MutableTestLiveOperationIdentitySchema,
		LaunchPolicy:         "test_live",
		NonPromotable:        true,
		Environment:          environment,
		DeclaredEnvironment:  environment,
		Target:               environment + "-local",
		MutableStateDigest:   "sha256:1111111111111111111111111111111111111111111111111111111111111111",
		ImageVersion:         "sha256:1111111111111111111111111111111111111111111111111111111111111111",
		ConfigurationDigest:  "sha256:2222222222222222222222222222222222222222222222222222222222222222",
		RuntimeConfigVersion: "sha256:2222222222222222222222222222222222222222222222222222222222222222",
	}
}

func blockedPublicTestLiveDescriptor() OperationSecurityDescriptor {
	return OperationSecurityDescriptor{
		CanonicalOperationID: "content.media_asset.GetMediaAsset",
		ContractGraphSHA256:  "sha256:1111111111111111111111111111111111111111111111111111111111111111",
		Method:               http.MethodGet,
		PathTemplate:         "/content/media-assets/{mediaAssetId}",
		OperationKind:        "query",
		AuthMode:             "public",
		ActorRequirement:     "none",
		Principal:            "public",
		OwnershipPolicy:      "public_ready_asset_only",
		TimeoutMilliseconds:  1500,
		CommercialStatus:     "blocked",
	}
}

func canonicalTestLiveEnvironment(environment string) map[string]string {
	return map[string]string{
		runtimeIdentitySchemaEnv:              MutableTestLiveOperationIdentitySchema,
		runtimeLaunchPolicyEnv:                "test_live",
		runtimeNonPromotableEnv:               "true",
		runtimeDeclaredEnvironmentEnv:         environment,
		runtimeTargetEnv:                      environment + "-local",
		runtimeMutableStateDigestEnv:          "sha256:1111111111111111111111111111111111111111111111111111111111111111",
		runtimeConfigurationDigestEnv:         "sha256:2222222222222222222222222222222222222222222222222222222222222222",
		runtimeImageVersionEnv:                "sha256:1111111111111111111111111111111111111111111111111111111111111111",
		runtimeServiceConfigurationVersionEnv: "sha256:2222222222222222222222222222222222222222222222222222222222222222",
	}
}

func mapLookup(values map[string]string) LookupEnvironment {
	return func(name string) (string, bool) {
		value, ok := values[name]
		return value, ok
	}
}

func TestMutableTestLiveOperationIdentityAcceptsCanonicalNonProductionTargets(t *testing.T) {
	t.Parallel()
	for _, environment := range []string{"alpha", "beta", "gamma"} {
		environment := environment
		t.Run(environment, func(t *testing.T) {
			t.Parallel()
			if err := validMutableTestLiveOperationIdentity(environment).Validate(); err != nil {
				t.Fatal(err)
			}
		})
	}
}

func TestMutableTestLiveOperationIdentityRejectsProductionAndDrift(t *testing.T) {
	t.Parallel()
	for _, testCase := range []struct {
		name   string
		mutate func(*MutableTestLiveOperationIdentity)
	}{
		{name: "prod", mutate: func(identity *MutableTestLiveOperationIdentity) {
			identity.Environment = "prod"
			identity.DeclaredEnvironment = "prod"
			identity.Target = "prod"
		}},
		{name: "prod release", mutate: func(identity *MutableTestLiveOperationIdentity) {
			identity.LaunchPolicy = "prod_release"
		}},
		{name: "promotable", mutate: func(identity *MutableTestLiveOperationIdentity) {
			identity.NonPromotable = false
		}},
		{name: "cross target", mutate: func(identity *MutableTestLiveOperationIdentity) {
			identity.Target = "beta-local"
		}},
		{name: "declared environment drift", mutate: func(identity *MutableTestLiveOperationIdentity) {
			identity.DeclaredEnvironment = "beta"
		}},
		{name: "image drift", mutate: func(identity *MutableTestLiveOperationIdentity) {
			identity.ImageVersion = "sha256:3333333333333333333333333333333333333333333333333333333333333333"
		}},
		{name: "config drift", mutate: func(identity *MutableTestLiveOperationIdentity) {
			identity.RuntimeConfigVersion = "sha256:3333333333333333333333333333333333333333333333333333333333333333"
		}},
	} {
		testCase := testCase
		t.Run(testCase.name, func(t *testing.T) {
			t.Parallel()
			identity := validMutableTestLiveOperationIdentity("alpha")
			testCase.mutate(&identity)
			if err := identity.Validate(); err == nil {
				t.Fatal("invalid mutable test-live identity passed validation")
			}
		})
	}
}

func TestTestLiveEdgeGuardStaysDefaultDenyAndOnlyDropsCommercialStatus(t *testing.T) {
	t.Parallel()
	guard, err := RequireGeneratedOperationAuthorizationForTestLive(
		[]OperationSecurityDescriptor{blockedPersonaDescriptor()},
		validMutableTestLiveOperationIdentity("alpha"),
	)
	if err != nil {
		t.Fatal(err)
	}
	served := 0
	handler := guard(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		served++
		w.WriteHeader(http.StatusNoContent)
	}))

	missingPrincipal := httptest.NewRecorder()
	handler.ServeHTTP(
		missingPrincipal,
		httptest.NewRequest(http.MethodGet, "/assistant/runs/run-1/events", nil),
	)
	if missingPrincipal.Code != http.StatusUnauthorized {
		t.Fatalf("missing principal status=%d", missingPrincipal.Code)
	}

	unknown := httptest.NewRecorder()
	handler.ServeHTTP(
		unknown,
		httptest.NewRequest(http.MethodGet, "/unknown", nil),
	)
	if unknown.Code != http.StatusNotFound {
		t.Fatalf("unknown route status=%d", unknown.Code)
	}

	accepted := httptest.NewRecorder()
	handler.ServeHTTP(accepted, personaRequest(t))
	if accepted.Code != http.StatusNoContent || served != 1 {
		t.Fatalf("accepted status=%d served=%d", accepted.Code, served)
	}
}

func TestOperationAuthorizationUsesTestLiveBoundaryOnlyForCanonicalIdentity(t *testing.T) {
	t.Parallel()
	descriptors := []OperationSecurityDescriptor{blockedPublicTestLiveDescriptor()}
	for _, environment := range []string{"alpha", "beta", "gamma"} {
		environment := environment
		t.Run(environment, func(t *testing.T) {
			t.Parallel()
			guard, err := OperationAuthorizationForRuntime(
				descriptors,
				environment,
				mapLookup(canonicalTestLiveEnvironment(environment)),
			)
			if err != nil {
				t.Fatal(err)
			}
			response := httptest.NewRecorder()
			guard(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
				w.WriteHeader(http.StatusNoContent)
			})).ServeHTTP(
				response,
				httptest.NewRequest(http.MethodGet, "/content/media-assets/asset-1", nil),
			)
			if response.Code != http.StatusNoContent {
				t.Fatalf("status=%d want=%d", response.Code, http.StatusNoContent)
			}
		})
	}
}

func TestOperationAuthorizationWithoutIdentityKeepsCommercialFailClosed(t *testing.T) {
	t.Parallel()
	guard, err := OperationAuthorizationForRuntime(
		[]OperationSecurityDescriptor{blockedPublicTestLiveDescriptor()},
		"alpha",
		mapLookup(map[string]string{}),
	)
	if err != nil {
		t.Fatal(err)
	}
	response := httptest.NewRecorder()
	guard(http.HandlerFunc(func(http.ResponseWriter, *http.Request) {
		t.Fatal("blocked operation reached handler without test-live identity")
	})).ServeHTTP(
		response,
		httptest.NewRequest(http.MethodGet, "/content/media-assets/asset-1", nil),
	)
	if response.Code != http.StatusForbidden {
		t.Fatalf("status=%d want=%d", response.Code, http.StatusForbidden)
	}
}

func TestOperationAuthorizationKeepsImmutableReleaseOnCommercialBoundary(t *testing.T) {
	t.Parallel()
	values := map[string]string{
		runtimeDeclaredEnvironmentEnv:         "alpha",
		runtimeTargetEnv:                      "alpha-local",
		runtimeConfigurationDigestEnv:         "sha256:2222222222222222222222222222222222222222222222222222222222222222",
		runtimeImageVersionEnv:                "sha256:1111111111111111111111111111111111111111111111111111111111111111",
		runtimeServiceConfigurationVersionEnv: "sha256:2222222222222222222222222222222222222222222222222222222222222222",
	}
	descriptor := blockedPublicTestLiveDescriptor()
	guard, err := OperationAuthorizationForRuntime(
		[]OperationSecurityDescriptor{descriptor},
		"alpha",
		mapLookup(values),
	)
	if err != nil {
		t.Fatalf("immutable release identity selected mutable test-live: %v", err)
	}
	blocked := httptest.NewRecorder()
	guard(http.HandlerFunc(func(http.ResponseWriter, *http.Request) {
		t.Fatal("commercial-blocked immutable release operation reached owner")
	})).ServeHTTP(
		blocked,
		httptest.NewRequest(http.MethodGet, "/content/media-assets/asset-1", nil),
	)
	if blocked.Code != http.StatusForbidden {
		t.Fatalf("blocked status=%d want=%d", blocked.Code, http.StatusForbidden)
	}

	descriptor.CommercialStatus = "ready"
	guard, err = OperationAuthorizationForRuntime(
		[]OperationSecurityDescriptor{descriptor},
		"alpha",
		mapLookup(values),
	)
	if err != nil {
		t.Fatal(err)
	}
	ready := httptest.NewRecorder()
	guard(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusNoContent)
	})).ServeHTTP(
		ready,
		httptest.NewRequest(http.MethodGet, "/content/media-assets/asset-1", nil),
	)
	if ready.Code != http.StatusNoContent {
		t.Fatalf("ready status=%d want=%d", ready.Code, http.StatusNoContent)
	}
}

func TestOperationAuthorizationRejectsMutableExclusiveIdentityWithoutSchema(t *testing.T) {
	t.Parallel()
	for _, name := range mutableTestLiveExclusiveIdentityEnvironment {
		name := name
		t.Run(name, func(t *testing.T) {
			t.Parallel()
			values := map[string]string{name: "true"}
			if name == runtimeLaunchPolicyEnv {
				values[name] = "test_live"
			}
			if name == runtimeMutableStateDigestEnv {
				values[name] = "sha256:1111111111111111111111111111111111111111111111111111111111111111"
			}
			if _, err := OperationAuthorizationForRuntime(
				[]OperationSecurityDescriptor{blockedPublicTestLiveDescriptor()},
				"alpha",
				mapLookup(values),
			); err == nil {
				t.Fatal("mutable-exclusive identity without schema was accepted")
			}
		})
	}
}

func TestOperationAuthorizationRejectsPartialProdAndDriftedIdentity(t *testing.T) {
	t.Parallel()
	for _, testCase := range []struct {
		name        string
		environment string
		mutate      func(map[string]string)
	}{
		{name: "partial", environment: "alpha", mutate: func(values map[string]string) {
			delete(values, runtimeTargetEnv)
		}},
		{name: "prod", environment: "prod", mutate: func(values map[string]string) {
			values[runtimeDeclaredEnvironmentEnv] = "prod"
			values[runtimeTargetEnv] = "prod"
		}},
		{name: "prod release", environment: "alpha", mutate: func(values map[string]string) {
			values[runtimeLaunchPolicyEnv] = "prod_release"
		}},
		{name: "cross target", environment: "alpha", mutate: func(values map[string]string) {
			values[runtimeTargetEnv] = "beta-local"
		}},
		{name: "image drift", environment: "alpha", mutate: func(values map[string]string) {
			values[runtimeImageVersionEnv] = "sha256:3333333333333333333333333333333333333333333333333333333333333333"
		}},
	} {
		testCase := testCase
		t.Run(testCase.name, func(t *testing.T) {
			t.Parallel()
			values := canonicalTestLiveEnvironment("alpha")
			testCase.mutate(values)
			if _, err := OperationAuthorizationForRuntime(
				[]OperationSecurityDescriptor{blockedPublicTestLiveDescriptor()},
				testCase.environment,
				mapLookup(values),
			); err == nil {
				t.Fatal("invalid operation boundary identity was accepted")
			}
		})
	}
}
