// spec_ref: specs/feature-tree/assistant-run-learning/skill-product-integration-platform/active-skill-package-catalog/spec.md#gwt-001
// 错误契约语义双向锁：SkillPackageRelease errors.yaml 声明的错误码由真实触发条件
// 经 HTTP 边界发射，并断言 canonical code 与 http_status。
package skill_package_release_test

import (
	"bytes"
	"context"
	"crypto/ed25519"
	"crypto/rand"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	packagehttp "quwoquan_service/services/assistant-service/internal/assistant/skill_package_release/adapters/inbound/http"
	"quwoquan_service/services/assistant-service/internal/assistant/skill_package_release/application"
	"quwoquan_service/services/assistant-service/internal/assistant/skill_package_release/domain/model"
)

// capabilityDeniedActivations 是对象级 typed double：命令读取路径冒出
// ErrCapabilityDenied，锁定 HTTP 边界把该 sentinel 映射为 canonical code。
type capabilityDeniedActivations struct{ *memoryRepository }

func (stub capabilityDeniedActivations) GetCommandResult(
	context.Context,
	string,
	string,
	string,
) (model.Activation, bool, error) {
	return model.Activation{}, false, model.ErrCapabilityDenied
}

func TestSkillPackageHTTPEmitsCanonicalErrorContract(t *testing.T) {
	t.Parallel()
	publicKey, privateKey, err := ed25519.GenerateKey(rand.Reader)
	if err != nil {
		t.Fatal(err)
	}
	_, foreignKey, err := ed25519.GenerateKey(rand.Reader)
	if err != nil {
		t.Fatal(err)
	}
	now := time.Date(2026, 8, 13, 9, 0, 0, 0, time.UTC)
	runtime := application.RuntimeIdentity{
		APIVersion: "assistant-skill/v1",
		Version:    "1.4.0",
	}
	newService := func(repository *memoryRepository) *application.Service {
		return application.NewService(
			repository,
			repository,
			repository,
			application.NewEd25519Verifier(
				map[string]ed25519.PublicKey{testKeyID: publicKey},
			),
			runtime,
			func() time.Time { return now },
		)
	}

	t.Run("missing command identity is skill_package_invalid", func(t *testing.T) {
		t.Parallel()
		mux := http.NewServeMux()
		packagehttp.NewHandler(newService(newMemoryRepository())).RegisterRoutes(mux)
		request := httptest.NewRequest(
			http.MethodPost,
			"/internal/assistant/skill-package-releases",
			bytes.NewReader([]byte(`{}`)),
		)
		recorder := httptest.NewRecorder()
		mux.ServeHTTP(recorder, request)
		assertSkillPackageWireError(
			t,
			recorder,
			http.StatusBadRequest,
			"ASSISTANT.USER.skill_package_invalid",
		)
	})

	t.Run("untrusted signature is skill_package_signature_invalid", func(t *testing.T) {
		t.Parallel()
		repository := newMemoryRepository()
		release := signedRelease(t, repository, "1.0.0", foreignKey)
		mux := http.NewServeMux()
		packagehttp.NewHandler(newService(repository)).RegisterRoutes(mux)
		recorder := packageRequest(
			t, mux, "/internal/assistant/skill-package-releases",
			"stage-signature-invalid", release,
		)
		assertSkillPackageWireError(
			t,
			recorder,
			http.StatusInternalServerError,
			"ASSISTANT.SYSTEM.skill_package_signature_invalid",
		)
	})

	t.Run("tampered digest is skill_package_digest_mismatch", func(t *testing.T) {
		t.Parallel()
		repository := newMemoryRepository()
		release := signedRelease(t, repository, "1.0.0", privateKey)
		release.ReleaseDigest = "sha256:" + strings.Repeat("f", 64)
		mux := http.NewServeMux()
		packagehttp.NewHandler(newService(repository)).RegisterRoutes(mux)
		recorder := packageRequest(
			t, mux, "/internal/assistant/skill-package-releases",
			"stage-digest-mismatch", release,
		)
		assertSkillPackageWireError(
			t,
			recorder,
			http.StatusBadRequest,
			"ASSISTANT.USER.skill_package_digest_mismatch",
		)
	})

	t.Run("missing evaluation receipt is skill_package_evaluation_receipt_invalid", func(t *testing.T) {
		t.Parallel()
		repository := newMemoryRepository()
		release := signedRelease(t, repository, "1.0.0", privateKey)
		mux := http.NewServeMux()
		packagehttp.NewHandler(newService(repository)).RegisterRoutes(mux)
		stage := packageRequest(
			t, mux, "/internal/assistant/skill-package-releases",
			"stage-receipt", release,
		)
		if stage.Code != http.StatusCreated {
			t.Fatalf("stage status=%d body=%s", stage.Code, stage.Body.String())
		}
		recorder := packageRequest(
			t, mux, "/internal/assistant/skill-package-releases:activate",
			"activate-no-receipt", map[string]any{
				"packageId":        testPackageID,
				"releaseDigest":    release.ReleaseDigest,
				"expectedRevision": 0,
			},
		)
		assertSkillPackageWireError(
			t,
			recorder,
			http.StatusBadRequest,
			"ASSISTANT.USER.skill_package_evaluation_receipt_invalid",
		)
	})

	t.Run("stale activation revision is skill_package_revision_conflict", func(t *testing.T) {
		t.Parallel()
		repository := newMemoryRepository()
		release := signedRelease(t, repository, "1.0.0", privateKey)
		mux := http.NewServeMux()
		packagehttp.NewHandler(newService(repository)).RegisterRoutes(mux)
		stage := packageRequest(
			t, mux, "/internal/assistant/skill-package-releases",
			"stage-revision", release,
		)
		if stage.Code != http.StatusCreated {
			t.Fatalf("stage status=%d body=%s", stage.Code, stage.Body.String())
		}
		recorder := packageRequest(
			t, mux, "/internal/assistant/skill-package-releases:activate",
			"activate-stale-revision", map[string]any{
				"packageId":         testPackageID,
				"releaseDigest":     release.ReleaseDigest,
				"expectedRevision":  5,
				"evaluationReceipt": passedEvaluationReceipt(t, release),
			},
		)
		assertSkillPackageWireError(
			t,
			recorder,
			http.StatusConflict,
			"ASSISTANT.USER.skill_package_revision_conflict",
		)
	})

	t.Run("absent release is skill_package_asset_unavailable", func(t *testing.T) {
		t.Parallel()
		repository := newMemoryRepository()
		mux := http.NewServeMux()
		packagehttp.NewHandler(newService(repository)).RegisterRoutes(mux)
		recorder := packageRequest(
			t, mux, "/internal/assistant/skill-package-releases:activate",
			"activate-missing-release", map[string]any{
				"packageId":        testPackageID,
				"releaseDigest":    "sha256:" + strings.Repeat("a", 64),
				"expectedRevision": 0,
			},
		)
		assertSkillPackageWireError(
			t,
			recorder,
			http.StatusServiceUnavailable,
			"ASSISTANT.DEPENDENCY.skill_package_asset_unavailable",
		)
	})

	t.Run("capability denial maps to skill_package_capability_denied", func(t *testing.T) {
		t.Parallel()
		repository := newMemoryRepository()
		release := signedRelease(t, repository, "1.0.0", privateKey)
		// 真实域行为：未声明的能力请求返回 ErrCapabilityDenied sentinel。
		if err := (application.ResolvedRelease{Release: release}).RequireCapabilities(
			[]model.CapabilityGrant{{CapabilityID: "tool.admin", Scope: "write"}},
		); !errors.Is(err, model.ErrCapabilityDenied) {
			t.Fatalf("undeclared capability error = %v", err)
		}
		// HTTP 边界合同：该 sentinel 从命令路径冒出时必须发射 canonical code。
		service := application.NewService(
			repository,
			capabilityDeniedActivations{repository},
			repository,
			application.NewEd25519Verifier(
				map[string]ed25519.PublicKey{testKeyID: publicKey},
			),
			runtime,
			func() time.Time { return now },
		)
		mux := http.NewServeMux()
		packagehttp.NewHandler(service).RegisterRoutes(mux)
		recorder := packageRequest(
			t, mux, "/internal/assistant/skill-package-releases:activate",
			"activate-capability-denied", map[string]any{
				"packageId":         testPackageID,
				"releaseDigest":     release.ReleaseDigest,
				"expectedRevision":  0,
				"evaluationReceipt": passedEvaluationReceipt(t, release),
			},
		)
		assertSkillPackageWireError(
			t,
			recorder,
			http.StatusForbidden,
			"ASSISTANT.USER.skill_package_capability_denied",
		)
	})
}

func assertSkillPackageWireError(
	t *testing.T,
	recorder *httptest.ResponseRecorder,
	wantStatus int,
	wantCode string,
) {
	t.Helper()
	var response struct {
		Code string `json:"code"`
	}
	if err := json.Unmarshal(recorder.Body.Bytes(), &response); err != nil {
		t.Fatalf("decode error response %q: %v", recorder.Body.String(), err)
	}
	if recorder.Code != wantStatus || response.Code != wantCode {
		t.Fatalf(
			"response=%d/%s, want %d/%s body=%s",
			recorder.Code,
			response.Code,
			wantStatus,
			wantCode,
			recorder.Body.String(),
		)
	}
}
