package account_session

import (
	"fmt"

	rtauth "quwoquan_service/runtime/auth"
)

// LocalAcceptanceTargets maps APP_ENV to the only allowed local integration
// topology labels for the Ops acceptance-session issuer.
var LocalAcceptanceTargets = map[string]string{
	"alpha": "alpha-local",
	"beta":  "beta-local",
	"gamma": "gamma-local",
	"prod":  "prod-sim",
}

// Subject builds the least-privilege TokenSubject for a local acceptance profile.
func Subject(
	profile string,
	ownerID string,
	personaID string,
) (rtauth.TokenSubject, error) {
	switch profile {
	case "", "persona":
		return rtauth.TokenSubject{
			AccountID: ownerID,
			PersonaID: personaID,
		}, nil
	case "content-report-operator":
		return rtauth.TokenSubject{
			AccountID: ownerID,
			PersonaID: personaID,
			Scopes: []string{
				"ops.case.read",
				"ops.case.write",
			},
			Permissions: []string{
				"content.report.read",
				"content.report.review",
				"content.report.resolve",
			},
			Roles: []string{"operator"},
		}, nil
	case "content-moderation-operator":
		return rtauth.TokenSubject{
			AccountID: ownerID,
			PersonaID: personaID,
			Scopes: []string{
				"ops.case.read",
				"ops.case.write",
			},
			Permissions: []string{
				"content.moderation.read",
				"content.moderation.review",
				"content.moderation.decide",
			},
			Roles: []string{"operator"},
		}, nil
	case "content-filter-catalog-publisher":
		return rtauth.TokenSubject{
			AccountID: ownerID,
			PersonaID: personaID,
			Scopes: []string{
				"content.filter_catalog.manage",
			},
			Roles: []string{"service"},
		}, nil
	default:
		return rtauth.TokenSubject{}, fmt.Errorf(
			"unsupported local acceptance profile %q",
			profile,
		)
	}
}
