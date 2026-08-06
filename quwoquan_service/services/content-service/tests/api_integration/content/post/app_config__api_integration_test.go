// spec_ref: specs/feature-tree/runtime/runtime-client-foundation/app-remote-config/spec.md#gwt-004
// readiness_case: get-app-config-api
package api_integration

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestGetAppConfigHTTPReturnsCacheableCanonicalSnapshot(t *testing.T) {
	request := httptest.NewRequest(http.MethodGet, "/config/app", nil)
	recorder := httptest.NewRecorder()
	testHandler.ServeHTTP(recorder, request)
	if recorder.Code != http.StatusOK {
		t.Fatalf("GetAppConfig status=%d body=%s", recorder.Code, recorder.Body.String())
	}
	var snapshot struct {
		Schema     string `json:"schema"`
		ConfigHash string `json:"configHash"`
		MaxAgeSec  int    `json:"maxAgeSec"`
	}
	if err := json.Unmarshal(recorder.Body.Bytes(), &snapshot); err != nil {
		t.Fatal(err)
	}
	if snapshot.Schema != "app_remote_config" ||
		!strings.HasPrefix(snapshot.ConfigHash, "sha256:") ||
		snapshot.MaxAgeSec <= 0 {
		t.Fatalf("GetAppConfig snapshot=%+v", snapshot)
	}
	etag := recorder.Header().Get("ETag")
	if etag != `"`+snapshot.ConfigHash+`"` {
		t.Fatalf("GetAppConfig ETag=%q hash=%q", etag, snapshot.ConfigHash)
	}
}
