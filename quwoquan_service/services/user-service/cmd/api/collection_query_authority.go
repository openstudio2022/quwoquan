package bootstrap

import (
	"encoding/base64"
	"encoding/json"
	"errors"
	"net/http"
	"os"
	"quwoquan_service/runtime/servicekit"
	inbound "quwoquan_service/services/user-service/internal/account/user_account/adapters/inbound/http"
	authority "quwoquan_service/services/user-service/internal/account/user_account/application"
	accountports "quwoquan_service/services/user-service/internal/account/user_account/domain/ports"
	"strings"
	"time"
)

func registerCollectionQueryAuthority(asm *servicekit.Assembly, cfg *config, accounts accountports.AccountSecurityReader, personas authority.PersonaOwnershipReader, mux *http.ServeMux) error {
	id := strings.TrimSpace(cfg.CollectionQueryAuthority.ActiveKeyID)
	ref := strings.TrimSpace(cfg.CollectionQueryAuthority.KeyringSecretRef)
	if id == "" || ref == "" {
		return errors.New("collection authority requires key identity and secret reference")
	}
	raw, exists := os.LookupEnv(ref)
	if !exists || raw == "" {
		return errors.New("collection authority keyring reference unavailable")
	}
	var encoded map[string]string
	if json.Unmarshal([]byte(raw), &encoded) != nil {
		return errors.New("collection authority keyring invalid")
	}
	keys := map[string][]byte{}
	for keyID, value := range encoded {
		key, err := base64.StdEncoding.DecodeString(value)
		if err != nil {
			return errors.New("collection authority key encoding invalid")
		}
		keys[keyID] = key
	}
	a, err := authority.NewCollectionQueryAuthority(asm.Auth.AccessVerifier, accounts, personas, authority.CollectionAuthorityKeys{ActiveID: id, VerificationKeys: keys}, time.Now)
	if err != nil {
		return err
	}
	inbound.NewCollectionQueryAuthorityHandler(a).RegisterRoutes(mux)
	return nil
}
