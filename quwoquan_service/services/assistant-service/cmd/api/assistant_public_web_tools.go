package bootstrap

import (
	"fmt"

	publicwebtool "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/adapters/outbound/tool"
	publicwebapplication "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/publicweb"
	toolpkg "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/tool"
	publicwebpersistence "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/infrastructure/publicweb"
)

func buildPublicWebToolHandlers(
	evidence *publicwebpersistence.MongoEvidenceStore,
	budget *publicwebpersistence.MongoRunBudgetGate,
) (map[string]toolpkg.Handler, error) {
	if evidence == nil || budget == nil {
		return nil, fmt.Errorf("public web evidence store and durable budget are required")
	}
	policy := publicwebpersistence.NewNetworkPolicy(nil)
	service := publicwebapplication.NewService(
		publicwebapplication.NewLedgerTargetResolver(evidence),
		publicwebpersistence.NewFetcher(
			policy,
			publicwebpersistence.DefaultFetchLimits(),
		),
		evidence,
		budget,
		publicwebapplication.DefaultDocumentParser(),
	)
	finder := publicwebapplication.NewFinder(evidence)
	return map[string]toolpkg.Handler{
		"web_open": publicwebtool.OpenHandler(service),
		"web_find": publicwebtool.FindHandler(finder),
	}, nil
}
