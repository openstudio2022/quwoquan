package bootstrap

import (
	"encoding/base64"
	"encoding/json"
	"errors"
	"os"
	"strings"

	relationshippersistence "quwoquan_service/services/user-service/internal/relationship/persona_relationship/infrastructure/persistence"
)

func loadRelationshipMutationBasisSigner(cfg *config, audience string) (*relationshippersistence.MutationBasisSigner, error) {
	activeID := strings.TrimSpace(cfg.RelationshipMutationBasis.ActiveKeyID)
	ref := strings.TrimSpace(cfg.RelationshipMutationBasis.KeyringSecretRef)
	if activeID == "" || ref == "" {
		return nil, errors.New("relationship mutation basis requires key identity and secret reference")
	}
	raw, ok := os.LookupEnv(ref)
	if !ok || strings.TrimSpace(raw) == "" {
		return nil, errors.New("relationship mutation basis keyring reference unavailable")
	}
	var encoded map[string]string
	if err := json.Unmarshal([]byte(raw), &encoded); err != nil {
		return nil, errors.New("relationship mutation basis keyring invalid")
	}
	keys := make([]relationshippersistence.MutationBasisKey, 0, len(encoded))
	for id, value := range encoded {
		material, err := base64.StdEncoding.DecodeString(value)
		if err != nil {
			return nil, errors.New("relationship mutation basis key encoding invalid")
		}
		keys = append(keys, relationshippersistence.MutationBasisKey{ID: id, Material: material})
	}
	return relationshippersistence.NewMutationBasisSigner(audience, activeID, keys)
}
