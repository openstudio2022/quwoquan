package main

import "testing"

func TestRouteDefResolveAuthMode_DefaultDeny(t *testing.T) {
	t.Parallel()

	if got := (routeDef{}).resolveAuthMode(); got != "required" {
		t.Fatalf("missing auth metadata must default to required, got %q", got)
	}
	if got := (routeDef{Auth: "optional"}).resolveAuthMode(); got != "optional" {
		t.Fatalf("explicit optional auth must be preserved, got %q", got)
	}
	if got := (routeDef{
		Security: routeSecurity{AuthMode: "public"},
	}).resolveAuthMode(); got != "public" {
		t.Fatalf("explicit public auth must be preserved, got %q", got)
	}
}

func TestRenderAuthPolicyDart_RejectsDuplicateShortOperation(t *testing.T) {
	t.Parallel()

	defer func() {
		if recover() == nil {
			t.Fatal("duplicate short operation id must fail generation")
		}
	}()

	renderAuthPolicyDart(map[string][]routeDef{
		"chat": {
			{Operation: "MarkAsRead", Auth: "required"},
		},
		"notification": {
			{Operation: "MarkAsRead", Auth: "required"},
		},
	})
}
