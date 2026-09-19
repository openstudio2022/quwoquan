package bootstrap

import (
	"encoding/base64"
	"encoding/json"
	"errors"
	"os"
	p "quwoquan_service/services/content-service/internal/content/content_reaction/infrastructure/persistence"
	"strings"
)

func loadReactionMutationBasisSigner(cfg *config, audience string) (*p.ReactionMutationBasisSigner, error) {
	id := strings.TrimSpace(cfg.ReactionMutationBasis.ActiveKeyID)
	ref := strings.TrimSpace(cfg.ReactionMutationBasis.KeyringSecretRef)
	if id == "" || ref == "" {
		return nil, errors.New("reaction mutation basis key config required")
	}
	raw, ok := os.LookupEnv(ref)
	if !ok {
		return nil, errors.New("reaction mutation basis keyring unavailable")
	}
	var values map[string]string
	if json.Unmarshal([]byte(raw), &values) != nil {
		return nil, errors.New("reaction mutation basis keyring invalid")
	}
	keys := []p.ReactionMutationBasisKey{}
	for keyID, value := range values {
		material, err := base64.StdEncoding.DecodeString(value)
		if err != nil {
			return nil, err
		}
		keys = append(keys, p.ReactionMutationBasisKey{ID: keyID, Material: material})
	}
	return p.NewReactionMutationBasisSigner(audience, id, keys)
}
