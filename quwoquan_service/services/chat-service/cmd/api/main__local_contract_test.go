package bootstrap

import (
	"reflect"
	"testing"
)

func TestChainCleanupCapturesEachPreviousCallback(t *testing.T) {
	calls := []string{}
	cleanup := func() { calls = append(calls, "base") }
	cleanup = chainCleanup(cleanup, func() { calls = append(calls, "first") })
	cleanup = chainCleanup(cleanup, func() { calls = append(calls, "second") })

	cleanup()

	if want := []string{"second", "first", "base"}; !reflect.DeepEqual(calls, want) {
		t.Fatalf("cleanup calls = %v, want %v", calls, want)
	}
}
