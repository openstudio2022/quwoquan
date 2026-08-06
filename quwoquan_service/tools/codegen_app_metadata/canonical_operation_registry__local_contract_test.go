package main

import (
	"fmt"
	"strings"
	"testing"
)

func TestGeneratedOperationRegistryRejectsCanonicalIdentifierCollisions(t *testing.T) {
	t.Parallel()

	tests := []struct {
		name string
		ids  []string
	}{
		{
			name: "duplicate canonical ID",
			ids:  []string{"example.object.Read", "example.object.Read"},
		},
		{
			name: "distinct IDs with the same Dart identifier",
			ids:  []string{"example.foo-bar.Read", "example.foo_bar.Read"},
		},
	}
	for _, test := range tests {
		test := test
		t.Run(test.name, func(t *testing.T) {
			t.Parallel()
			defer func() {
				recovered := recover()
				if recovered == nil {
					t.Fatal("canonical operation registry collision must fail generation")
				}
				if !strings.Contains(
					fmt.Sprint(recovered),
					"canonical operation identifier collision",
				) {
					t.Fatalf("unexpected collision failure: %v", recovered)
				}
			}()

			lock := appContractLock{}
			for _, operationID := range test.ids {
				lock.AppExposedOperations = append(
					lock.AppExposedOperations,
					appExposedOperation{CanonicalOperationID: operationID},
				)
			}
			_ = writeGeneratedOperationContracts(t.TempDir(), lock, nil)
		})
	}
}
