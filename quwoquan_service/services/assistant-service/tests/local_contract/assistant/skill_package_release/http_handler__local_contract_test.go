// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/app-cloud-business-object-commercial-closure/spec.md#gwt-001
package skill_package_release_test

import (
	"bytes"
	"crypto/ed25519"
	"crypto/rand"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	rtauth "quwoquan_service/runtime/auth"
	packagehttp "quwoquan_service/services/assistant-service/internal/assistant/skill_package_release/adapters/inbound/http"
	"quwoquan_service/services/assistant-service/internal/assistant/skill_package_release/application"
	"quwoquan_service/services/assistant-service/internal/assistant/skill_package_release/domain/model"
)

func TestSkillPackageHTTPUsesTrustedPublisherAndOneCommandIdentity(t *testing.T) {
	publicKey, privateKey, err := ed25519.GenerateKey(rand.Reader)
	if err != nil {
		t.Fatal(err)
	}
	repository := newMemoryRepository()
	release := signedRelease(t, repository, "1.0.0", privateKey)
	service := application.NewService(
		repository,
		repository,
		repository,
		application.NewEd25519Verifier(map[string]ed25519.PublicKey{testKeyID: publicKey}),
		application.RuntimeIdentity{APIVersion: "assistant-skill/v1", Version: "1.4.0"},
		func() time.Time { return time.Date(2026, 8, 2, 12, 0, 0, 0, time.UTC) },
	)
	mux := http.NewServeMux()
	packagehttp.NewHandler(service).RegisterRoutes(mux)

	stage := packageRequest(t, mux, "/internal/assistant/skill-package-releases", "stage-1", release)
	if stage.Code != http.StatusCreated {
		t.Fatalf("stage status=%d body=%s", stage.Code, stage.Body.String())
	}
	activate := packageRequest(t, mux, "/internal/assistant/skill-package-releases:activate", "activate-1", map[string]any{
		"packageId": testPackageID, "releaseDigest": release.ReleaseDigest, "expectedRevision": 0,
	})
	if activate.Code != http.StatusOK {
		t.Fatalf("activate status=%d body=%s", activate.Code, activate.Body.String())
	}
	var activation model.Activation
	if err := json.Unmarshal(activate.Body.Bytes(), &activation); err != nil {
		t.Fatal(err)
	}
	if activation.ActivatedBy != "skill-package-publisher" || activation.Revision != 1 {
		t.Fatalf("activation=%+v", activation)
	}

	missingIdentity := httptest.NewRequest(
		http.MethodPost,
		"/internal/assistant/skill-package-releases:rollback",
		bytes.NewReader([]byte(`{"packageId":"assistant.session.skills","expectedRevision":1}`)),
	)
	recorder := httptest.NewRecorder()
	mux.ServeHTTP(recorder, missingIdentity)
	if recorder.Code != http.StatusBadRequest {
		t.Fatalf("missing identity status=%d body=%s", recorder.Code, recorder.Body.String())
	}
}

func packageRequest(
	t *testing.T,
	handler http.Handler,
	path string,
	commandID string,
	body any,
) *httptest.ResponseRecorder {
	t.Helper()
	payload, err := json.Marshal(body)
	if err != nil {
		t.Fatal(err)
	}
	request := httptest.NewRequest(http.MethodPost, path, bytes.NewReader(payload))
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("Idempotency-Key", commandID)
	request = request.WithContext(rtauth.WithPrincipal(request.Context(), rtauth.Principal{
		Claims: rtauth.Claims{Subject: "skill-package-publisher"},
	}))
	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, request)
	return recorder
}
