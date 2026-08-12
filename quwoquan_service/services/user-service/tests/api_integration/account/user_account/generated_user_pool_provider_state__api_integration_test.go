package api_integration

import (
	"encoding/json"
	"fmt"
	"net/http"
	"testing"

	"quwoquan_service/services/user-service/tests/support/testobject"
)

type sharedPoolUser struct {
	UserID          string   `json:"userId"`
	DisplayName     string   `json:"displayName"`
	AvatarObjectKey string   `json:"avatarObjectKey"`
	Bio             string   `json:"bio"`
	PersonaRefs     []string `json:"personaRefs"`
}

type sharedPoolPersona struct {
	UserID          string
	PersonaID       string
	DisplayName     string
	AvatarObjectKey string
	Bio             string
}

func loadSharedPoolPersonas(t *testing.T) []sharedPoolPersona {
	t.Helper()
	users := testobject.BuildUserPool(32)
	personas := make([]sharedPoolPersona, 0, len(users))
	for _, user := range users {
		for _, personaID := range user.PersonaRefs {
			personas = append(personas, sharedPoolPersona{
				UserID:          user.UserID,
				PersonaID:       personaID,
				DisplayName:     user.DisplayName,
				AvatarObjectKey: user.AvatarObjectKey,
				Bio:             user.Bio,
			})
		}
	}
	if len(personas) == 0 {
		t.Fatal("shared user pool must contain at least one persona")
	}
	return personas
}

func provisionGeneratedUserPool(t *testing.T, definitions []sharedPoolPersona) []sharedPoolPersona {
	t.Helper()
	provisioned := make([]sharedPoolPersona, 0, len(definitions))
	for index, definition := range definitions {
		login := doRequest(
			t,
			http.MethodPost,
			"/auth/login/anonymous",
			fmt.Sprintf(
				`{"installId":"generated-pool-%03d","deviceFingerprintHash":"generated-pool-%03d","platform":"ios","appVersion":"1.0.0"}`,
				index+1,
				index+1,
			),
			nil,
		)
		if login.Code != http.StatusOK {
			t.Fatalf("anonymous provider-state login %d: got %d: %s", index, login.Code, login.Body.String())
		}
		loginBody := parseJSON(t, login)
		ownerID, _ := loginBody["ownerId"].(string)
		activePersona, _ := loginBody["activePersona"].(map[string]any)
		personaID, _ := activePersona["personaId"].(string)
		if ownerID == "" || personaID == "" {
			t.Fatalf("anonymous provider-state identity is incomplete: %#v", loginBody)
		}

		profileBody, err := json.Marshal(map[string]string{
			"nickname": definition.DisplayName,
			"bio":      definition.Bio,
		})
		if err != nil {
			t.Fatalf("encode generated profile command: %v", err)
		}
		updated := doRequest(
			t,
			http.MethodPatch,
			"/user/profile",
			string(profileBody),
			authHeadersForPersona(ownerID, personaID),
		)
		if updated.Code != http.StatusOK {
			t.Fatalf("profile provider-state command %d: got %d: %s", index, updated.Code, updated.Body.String())
		}
		provisioned = append(provisioned, sharedPoolPersona{
			UserID:          ownerID,
			PersonaID:       personaID,
			DisplayName:     definition.DisplayName,
			AvatarObjectKey: definition.AvatarObjectKey,
			Bio:             definition.Bio,
		})
	}
	return provisioned
}

func TestGeneratedUserPoolProviderStateReadsViaHandler(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	personas := provisionGeneratedUserPool(t, loadSharedPoolPersonas(t))
	viewer := personas[0]
	verifiedProfiles := map[string]struct{}{}
	for _, target := range personas {
		if _, exists := verifiedProfiles[target.UserID]; !exists {
			profileRec := doRequest(
				t,
				http.MethodGet,
				"/user/profile/"+target.UserID,
				"",
				authHeaders(target.UserID),
			)
			if profileRec.Code != http.StatusOK {
				t.Fatalf("profile %s expected 200, got %d: %s", target.UserID, profileRec.Code, profileRec.Body.String())
			}
			verifiedProfiles[target.UserID] = struct{}{}
		}

		bundleRec := doRequest(
			t,
			http.MethodGet,
			"/user/personas/"+target.PersonaID+"/homepage-bundle",
			"",
			authHeadersForPersona(viewer.UserID, viewer.PersonaID),
		)
		if bundleRec.Code != http.StatusOK {
			t.Fatalf("homepage-bundle %s expected 200, got %d: %s", target.PersonaID, bundleRec.Code, bundleRec.Body.String())
		}
	}
}
