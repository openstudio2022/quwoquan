package creatorsearch_test

import (
	"bytes"
	rt "quwoquan_service/runtime/search"
	app "quwoquan_service/services/content-service/internal/content/post/application/public"
	"strings"
	"testing"
)

// spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-007
// 旧Creator-only已无运行入口，不能把其输入解释成统一纯准备。
func TestUnifiedPrepareRejectsRetiredBodyAndCannotActivate(t *testing.T) {
	var command app.PreparePostReleaseQueriesCommand
	if rt.DecodeCreatorValue(bytes.NewBufferString(`{"binding":{},"expectedPreparationVersion":0,"idempotencyKey":"old"}`), &command) == nil {
		t.Fatal("retired body accepted")
	}
	release := rt.ReleaseCandidateBinding{"gamma", "qwq_data", "candidate", "sha256:" + strings.Repeat("a", 64)}
	if err := app.VerifyReleaseQueryActivation(t.Context(), release); err != app.ErrReleaseQueryNotReady {
		t.Fatal("prepare implied activation", err)
	}
}
