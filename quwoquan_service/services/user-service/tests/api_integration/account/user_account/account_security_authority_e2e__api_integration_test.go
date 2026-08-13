// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/account-lifecycle-self-service-account-closure/spec.md#gwt-004
// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/account-lifecycle-self-service-account-closure/spec.md#gwt-004.t1
// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/spec.md#sit-003
package api_integration

import (
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	rtauth "quwoquan_service/runtime/auth"
)

func TestAccountSecurityAuthority_RejectsClosedAndStaleTokenAtResourceBoundary(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	userServer := httptest.NewServer(testHandler)
	defer userServer.Close()

	t.Run("closed account", func(t *testing.T) {
		const accountID = "authority_e2e_closed"
		createTestProfile(t, accountID, "authority_e2e_closed")
		token := mustAuthorityE2EAccessToken(t, accountID, 1)
		resource, downstreamCalls := authorityE2EResource(t, userServer)

		activeRequest := httptest.NewRequest(http.MethodGet, "/resource", nil)
		activeRequest.Header.Set("Authorization", "Bearer "+token)
		activeResponse := httptest.NewRecorder()
		resource.ServeHTTP(activeResponse, activeRequest)
		if activeResponse.Code != http.StatusNoContent || *downstreamCalls != 1 {
			t.Fatalf(
				"active token must reach resource: status=%d calls=%d",
				activeResponse.Code,
				*downstreamCalls,
			)
		}

		closeResponse := doRequest(
			t,
			http.MethodPost,
			"/owner/account/close",
			"",
			map[string]string{"Authorization": "Bearer " + token},
		)
		if closeResponse.Code != http.StatusOK {
			t.Fatalf(
				"close account: expected 200, got %d: %s",
				closeResponse.Code,
				closeResponse.Body.String(),
			)
		}

		replayRequest := httptest.NewRequest(http.MethodGet, "/resource", nil)
		replayRequest.Header.Set("Authorization", "Bearer "+token)
		replayResponse := httptest.NewRecorder()
		resource.ServeHTTP(replayResponse, replayRequest)
		if replayResponse.Code != http.StatusGone || *downstreamCalls != 1 {
			t.Fatalf(
				"closed token must be rejected before resource: status=%d calls=%d body=%s",
				replayResponse.Code,
				*downstreamCalls,
				replayResponse.Body.String(),
			)
		}
		if body := parseJSON(t, replayResponse); body["code"] != "USER.AUTH.account_deleted" {
			t.Fatalf("closed authority error drift: %#v", body)
		}
	})

	t.Run("stale epoch", func(t *testing.T) {
		const accountID = "authority_e2e_stale"
		createTestProfile(t, accountID, "authority_e2e_stale")
		token := mustAuthorityE2EAccessToken(t, accountID, 1)
		seedAuthEpochAdvance(t, accountID)
		resource, downstreamCalls := authorityE2EResource(t, userServer)
		request := httptest.NewRequest(http.MethodGet, "/resource", nil)
		request.Header.Set("Authorization", "Bearer "+token)
		response := httptest.NewRecorder()

		resource.ServeHTTP(response, request)

		if response.Code != http.StatusUnauthorized || *downstreamCalls != 0 {
			t.Fatalf(
				"stale token must be rejected before resource: status=%d calls=%d body=%s",
				response.Code,
				*downstreamCalls,
				response.Body.String(),
			)
		}
		if body := parseJSON(t, response); body["code"] != "USER.AUTH.token_stale" {
			t.Fatalf("stale authority error drift: %#v", body)
		}
	})
}

func TestAccountSecurityAuthority_FailsClosedAtResourceBoundaryWhenUnavailable(
	t *testing.T,
) {
	unavailableServer := httptest.NewServer(http.NotFoundHandler())
	authorityURL := unavailableServer.URL
	unavailableServer.Close()

	resource, downstreamCalls := authorityE2EResourceForEndpoint(
		t,
		authorityURL,
		&http.Client{Timeout: 100 * time.Millisecond},
	)
	request := httptest.NewRequest(http.MethodGet, "/resource", nil)
	request.Header.Set(
		"Authorization",
		"Bearer "+mustAuthorityE2EAccessToken(t, "authority_e2e_unavailable", 1),
	)
	response := httptest.NewRecorder()

	resource.ServeHTTP(response, request)

	if response.Code != http.StatusServiceUnavailable || *downstreamCalls != 0 {
		t.Fatalf(
			"unavailable authority must reject before resource: status=%d calls=%d body=%s",
			response.Code,
			*downstreamCalls,
			response.Body.String(),
		)
	}
	if body := parseJSON(t, response); body["code"] != "USER.AUTH.account_security_unavailable" {
		t.Fatalf("unavailable authority error drift: %#v", body)
	}
}

func authorityE2EResource(
	t *testing.T,
	userServer *httptest.Server,
) (http.Handler, *int) {
	t.Helper()
	return authorityE2EResourceForEndpoint(t, userServer.URL, userServer.Client())
}

func authorityE2EResourceForEndpoint(
	t *testing.T,
	authorityBaseURL string,
	httpClient *http.Client,
) (http.Handler, *int) {
	t.Helper()
	credentials, err := rtauth.NewHS256ServiceAuthorizationProvider(
		testAccessConfig,
		"entity-service",
		[]string{"user.account.security.read"},
	)
	if err != nil {
		t.Fatal(err)
	}
	authority, err := rtauth.NewHTTPAccountSecurityAuthority(
		rtauth.HTTPAccountSecurityAuthorityConfig{
			BaseURL:     authorityBaseURL,
			HTTPClient:  httpClient,
			Credentials: credentials,
			Timeout:     time.Second,
		},
	)
	if err != nil {
		t.Fatal(err)
	}
	downstreamCalls := 0
	handler := rtauth.Middleware(rtauth.MiddlewareConfig{
		AccessTokenVerifier:      testAccessVerifier,
		AccountSecurityAuthority: authority,
	})(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		downstreamCalls++
		w.WriteHeader(http.StatusNoContent)
	}))
	return handler, &downstreamCalls
}

func mustAuthorityE2EAccessToken(
	t *testing.T,
	accountID string,
	authEpoch int64,
) string {
	t.Helper()
	token, err := testAccessSigner.Sign(rtauth.TokenSubject{
		AccountID: accountID,
		AuthEpoch: authEpoch,
	})
	if err != nil {
		t.Fatal(err)
	}
	return token
}
