package local_contract

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	httpadapter "quwoquan_service/services/api-edge/internal/edge_security/rollout_assignment/adapters/inbound/http"
	"quwoquan_service/services/api-edge/internal/edge_security/rollout_assignment/application"
)

func TestMinimumBuildSupportsObserveEnforceAndRecoveryExemption(t *testing.T) {
	policy := application.MinimumBuildPolicy{
		SourceDigest: "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
		Mode:         "enforce", Platforms: map[string]uint64{"android": 17000, "ios": 17000, "web": 17000},
	}
	middleware, err := httpadapter.MinimumBuildMiddleware(
		policy, map[string]struct{}{"/ops/app-recovery/version": {}}, nil,
	)
	if err != nil {
		t.Fatal(err)
	}
	handler := middleware(http.HandlerFunc(func(response http.ResponseWriter, _ *http.Request) {
		response.WriteHeader(http.StatusNoContent)
	}))

	blocked := httptest.NewRequest(http.MethodGet, "/content/feed", nil)
	blocked.Header.Set("X-Client-Device-Platform", "android")
	blocked.Header.Set("X-Client-App-Build", "16000")
	blockedResponse := httptest.NewRecorder()
	handler.ServeHTTP(blockedResponse, blocked)
	if blockedResponse.Code != http.StatusUpgradeRequired {
		t.Fatalf("blocked status=%d body=%s", blockedResponse.Code, blockedResponse.Body.String())
	}
	// 错误码契约：低于最低支持版本必须发射声明的稳定升级码。
	var upgradeBody struct {
		Code string `json:"code"`
	}
	if err := json.Unmarshal(blockedResponse.Body.Bytes(), &upgradeBody); err != nil {
		t.Fatalf("decode upgrade required body: %v", err)
	}
	if upgradeBody.Code != "GATEWAY.USER.client_upgrade_required" {
		t.Fatalf("code=%s want GATEWAY.USER.client_upgrade_required", upgradeBody.Code)
	}

	recovery := httptest.NewRequest(http.MethodGet, "/ops/app-recovery/version", nil)
	recovery.Header.Set("X-Client-Device-Platform", "android")
	recovery.Header.Set("X-Client-App-Build", "1")
	recoveryResponse := httptest.NewRecorder()
	handler.ServeHTTP(recoveryResponse, recovery)
	if recoveryResponse.Code != http.StatusNoContent {
		t.Fatalf("recovery status=%d", recoveryResponse.Code)
	}

	policy.Mode = "observe"
	decision := policy.Decide("android", "1")
	if !decision.Allowed || !decision.WouldBlock {
		t.Fatalf("observe decision=%+v", decision)
	}
}

func TestMinimumBuildRequiresAllThreePlatformsAndSourceDigest(t *testing.T) {
	policy := application.MinimumBuildPolicy{Mode: "enforce", Platforms: map[string]uint64{"android": 1}}
	if err := policy.Validate(); err == nil {
		t.Fatal("incomplete minimum build projection must fail")
	}
}
