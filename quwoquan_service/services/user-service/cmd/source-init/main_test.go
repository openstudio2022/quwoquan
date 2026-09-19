package main

import "testing"

// spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-001
func TestAcceptedSourceInitIdentity(t *testing.T) {
	cases := []struct {
		env, target, dsn string
		ok               bool
	}{
		{"alpha", "", "postgres://x", true},
		{"alpha", "alpha-local", "postgres://x", true},
		{"alpha", "beta-local", "postgres://x", false},
		{"gamma", "gamma-local", "postgres://x", true},
		{"prod", "prod-sim", "postgres://x", true},
		{"prod", "prod-hosted", "postgres://x", false},
		{"prod", "", "postgres://x", false},
		{"prod", "prod-sim", "", false},
		{"release", "prod-sim", "postgres://x", false},
	}
	for _, tc := range cases {
		err := acceptedSourceInitIdentity(tc.env, tc.target, tc.dsn)
		if tc.ok && err != nil {
			t.Fatalf("%+v: unexpected %v", tc, err)
		}
		if !tc.ok && err == nil {
			t.Fatalf("%+v: accepted forbidden identity", tc)
		}
	}
}
