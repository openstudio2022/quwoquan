// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/account-lifecycle-self-service-account-closure/spec.md#gwt-004
package api_integration

import (
	"net/http"
	"strings"
	"testing"
)

func TestReadAccountSecurity_ExposesOnlyScopedAuthoritySnapshot(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	const accountID = "security_authority_owner"
	createTestProfile(t, accountID, "security_authority_owner")

	response := doRequest(
		t,
		http.MethodGet,
		"/internal/user/accounts/"+accountID+"/security",
		"",
		serviceHeadersFor(
			"service:content-service",
			"user.account.security.read",
		),
	)
	if response.Code != http.StatusOK {
		t.Fatalf(
			"read account security: expected 200, got %d: %s",
			response.Code,
			response.Body.String(),
		)
	}
	if cacheControl := response.Header().Get("Cache-Control"); !strings.Contains(cacheControl, "no-store") {
		t.Fatalf("authority response must forbid caching, got %q", cacheControl)
	}
	body := parseJSON(t, response)
	if body["accountState"] != "active" {
		t.Fatalf("account state=%#v", body)
	}
	if _, ok := body["authEpoch"]; !ok {
		t.Fatalf("authEpoch missing: %#v", body)
	}
	for _, forbidden := range []string{
		"userId",
		"personaIds",
		"nickname",
		"phone",
		"deviceId",
		"credential",
		"caseRef",
	} {
		if _, exists := body[forbidden]; exists {
			t.Fatalf("authority snapshot leaked %q: %#v", forbidden, body)
		}
	}
}

func TestReadAccountSecurity_AllRegisteredResourceServicesAreAuthorized(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	const accountID = "security_authority_registered_services"
	createTestProfile(t, accountID, "security_authority_registered_services")

	for _, servicePrincipal := range []string{
		"service:api-edge",
		"service:assistant-service",
		"service:chat-service",
		"service:circle-service",
		"service:content-service",
		"service:entity-service",
		"service:integration-service",
		"service:notification-service",
		"service:product-ops-service",
		"service:realtime-gateway",
		"service:rtc-service",
		"service:search-service",
		"service:tag-service",
	} {
		t.Run(servicePrincipal, func(t *testing.T) {
			response := doRequest(
				t,
				http.MethodGet,
				"/internal/user/accounts/"+accountID+"/security",
				"",
				serviceHeadersFor(
					servicePrincipal,
					"user.account.security.read",
				),
			)
			if response.Code != http.StatusOK {
				t.Fatalf(
					"registered service authority read: expected 200, got %d: %s",
					response.Code,
					response.Body.String(),
				)
			}
		})
	}
}

func TestReadAccountSecurity_RejectsUnscopedOrNonServiceCallers(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	const accountID = "security_authority_denied"
	createTestProfile(t, accountID, "security_authority_denied")

	for name, headers := range map[string]map[string]string{
		"end user": authHeaders(accountID),
		"missing scope": serviceHeadersFor(
			"service:content-service",
			"content.post.read",
		),
		"untrusted scoped service": serviceHeadersFor(
			"service:untrusted-service",
			"user.account.security.read",
		),
	} {
		t.Run(name, func(t *testing.T) {
			response := doRequest(
				t,
				http.MethodGet,
				"/internal/user/accounts/"+accountID+"/security",
				"",
				headers,
			)
			if response.Code != http.StatusForbidden {
				t.Fatalf(
					"unauthorized authority read: expected 403, got %d: %s",
					response.Code,
					response.Body.String(),
				)
			}
		})
	}
}

func TestCheckAccountSecurityAuthority_RejectsUntrustedScopedService(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	response := doRequest(
		t,
		http.MethodGet,
		"/internal/user/account-security/health",
		"",
		serviceHeadersFor(
			"service:untrusted-service",
			"user.account.security.read",
		),
	)
	if response.Code != http.StatusForbidden {
		t.Fatalf(
			"untrusted authority health: expected 403, got %d: %s",
			response.Code,
			response.Body.String(),
		)
	}
}

func TestReadAccountSecurity_MissingSubjectIsNotConflatedWithAuthorityFailure(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	response := doRequest(
		t,
		http.MethodGet,
		"/internal/user/accounts/not_a_real_security_subject/security",
		"",
		serviceHeadersFor(
			"service:content-service",
			"user.account.security.read",
		),
	)
	if response.Code != http.StatusNotFound {
		t.Fatalf(
			"missing subject: expected 404, got %d: %s",
			response.Code,
			response.Body.String(),
		)
	}
}

func TestCheckAccountSecurityAuthority_VerifiesScopedReadinessWithoutSubject(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	for _, servicePrincipal := range []string{
		"service:api-edge",
		"service:search-service",
		"service:tag-service",
	} {
		t.Run(servicePrincipal, func(t *testing.T) {
			response := doRequest(
				t,
				http.MethodGet,
				"/internal/user/account-security/health",
				"",
				serviceHeadersFor(
					servicePrincipal,
					"user.account.security.read",
				),
			)
			if response.Code != http.StatusOK {
				t.Fatalf(
					"authority health: expected 200, got %d: %s",
					response.Code,
					response.Body.String(),
				)
			}
			if cacheControl := response.Header().Get("Cache-Control"); !strings.Contains(cacheControl, "no-store") {
				t.Fatalf("authority health must forbid caching, got %q", cacheControl)
			}
			body := parseJSON(t, response)
			if len(body) != 1 || body["status"] != "ok" {
				t.Fatalf("authority health must be data-free: %#v", body)
			}
		})
	}
}
