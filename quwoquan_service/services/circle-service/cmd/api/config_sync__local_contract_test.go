package main

import "testing"

func TestDefaultClusterNamePerEnvironment(t *testing.T) {
	cases := []struct {
		env  string
		want string
	}{
		{env: "alpha", want: "alpha-control-a"},
		{env: "beta", want: "beta-control-a"},
		{env: "gamma", want: "gamma-control-a"},
		{env: "prod", want: "prod-control-a"},
	}
	for _, tc := range cases {
		if got := defaultClusterName(tc.env); got != tc.want {
			t.Fatalf("defaultClusterName(%q) = %q, want %q", tc.env, got, tc.want)
		}
	}
}
