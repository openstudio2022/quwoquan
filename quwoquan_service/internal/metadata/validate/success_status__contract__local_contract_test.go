package validate

import (
	"testing"

	"quwoquan_service/internal/metadata/ast"
)

func TestSuccessStatusAcceptsTypedAcceptedReceipt(t *testing.T) {
	operation := ast.Operation{
		ID:               "search.search_request_fact.RecoverSearchAccountClosureDeadLetter",
		ResponseBodyKind: "object",
		ResponseEntity:   "SearchAccountClosureDeadLetterRecoveryAccepted",
		SuccessStatus:    202,
		SourcePath:       "search/search_request_fact/operations.yaml",
	}
	if issues := successStatusIssues(operation); len(issues) != 0 {
		t.Fatalf("typed 202 receipt rejected: %+v", issues)
	}
}

func TestSuccessStatusRejectsBodyStatusContradictions(t *testing.T) {
	tests := []struct {
		name      string
		operation ast.Operation
		code      string
	}{
		{
			name: "ack cannot claim accepted body",
			operation: ast.Operation{
				ID:               "search.search_request_fact.RecoverSearchAccountClosureDeadLetter",
				ResponseBodyKind: "ack", SuccessStatus: 202,
			},
			code: "CONTRACT.OPERATION.SUCCESS_STATUS_BODY_MISMATCH",
		},
		{
			name: "no-content cannot name response entity",
			operation: ast.Operation{
				ID:               "search.search_request_fact.RecoverSearchAccountClosureDeadLetter",
				ResponseBodyKind: "object", ResponseEntity: "RecoveryAccepted", SuccessStatus: 204,
			},
			code: "CONTRACT.OPERATION.SUCCESS_STATUS_BODY_MISMATCH",
		},
		{
			name: "upgrade owns protocol status",
			operation: ast.Operation{
				ID:               "realtime.connection.WebSocketUpgrade",
				ResponseBodyKind: "upgrade", SuccessStatus: 200,
			},
			code: "CONTRACT.OPERATION.SUCCESS_STATUS_FORBIDDEN",
		},
		{
			name: "non-no-content status requires typed body",
			operation: ast.Operation{
				ID:            "search.search_request_fact.RecoverSearchAccountClosureDeadLetter",
				SuccessStatus: 202,
			},
			code: "CONTRACT.OPERATION.SUCCESS_STATUS_BODY_MISMATCH",
		},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			issues := successStatusIssues(test.operation)
			if len(issues) != 1 || issues[0].Code != test.code {
				t.Fatalf("issues=%+v, want one %s", issues, test.code)
			}
		})
	}
}
