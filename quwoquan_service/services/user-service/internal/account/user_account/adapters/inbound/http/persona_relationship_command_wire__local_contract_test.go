package http

import (
	"net/http/httptest"
	"strings"
	"testing"
)

func TestDecodeRelationshipMutationIsStrictAndRequiresEvidence(t *testing.T) {
	cases := []struct {
		name, body string
		ok         bool
	}{
		{"valid", `{"mutationBasis":"basis","expectedVersion":0}`, true},
		{"unknown legacy clientRequestId", `{"mutationBasis":"basis","expectedVersion":0,"clientRequestId":"legacy"}`, false},
		{"missing basis", `{"expectedVersion":0}`, false},
		{"missing version", `{"mutationBasis":"basis"}`, false},
		{"negative version", `{"mutationBasis":"basis","expectedVersion":-1}`, false},
		{"trailing value", `{"mutationBasis":"basis","expectedVersion":0}{}`, false},
		{"malformed", `{"mutationBasis":`, false},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			r := httptest.NewRequest("POST", "/", strings.NewReader(tc.body))
			_, err := decodeRelationshipMutation(r)
			if tc.ok && err != nil {
				t.Fatal(err)
			}
			if !tc.ok && err == nil {
				t.Fatal("invalid body accepted")
			}
		})
	}
}
