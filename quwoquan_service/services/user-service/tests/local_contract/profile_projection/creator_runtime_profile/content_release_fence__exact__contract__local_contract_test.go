// readiness_case: content-release-fence-local
// spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-001
package local_contract

import (
	"context"
	"testing"

	userports "quwoquan_service/services/user-service/internal/account/user_account/domain/user/ports"
)

func TestUnavailableContentReleaseFenceDoesNotInventCurrentOrLatest(t *testing.T) {
	fence, found, err := (userports.UnavailableContentReleaseFenceReader{}).ActiveContentReleaseFence(context.Background())
	if err != nil || found || fence != (userports.ContentReleaseFence{}) {
		t.Fatalf("unavailable Content fence seam must fail closed: fence=%+v found=%v err=%v", fence, found, err)
	}
}
