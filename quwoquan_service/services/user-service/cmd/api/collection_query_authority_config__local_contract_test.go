package bootstrap

// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/collection-query-delegation/spec.md#gwt-002
import (
	"net/http"
	"testing"
)

func TestCollectionAuthorityMissingOrInvalidKeyConfigFailsClosed(t *testing.T) {
	for _, cfg := range []*config{{}, {CollectionQueryAuthority: struct {
		ActiveKeyID      string `yaml:"active_key_id" env:"COLLECTION_QUERY_AUTHORITY_ACTIVE_KEY_ID"`
		KeyringSecretRef string `yaml:"keyring_secret_ref" env:"COLLECTION_QUERY_AUTHORITY_KEYRING_SECRET_REF"`
	}{ActiveKeyID: "key"}}} {
		if err := registerCollectionQueryAuthority(nil, cfg, nil, nil, http.NewServeMux()); err == nil {
			t.Fatal("missing authority key config admitted")
		}
	}
	cfg := &config{}
	cfg.CollectionQueryAuthority.ActiveKeyID = "key"
	cfg.CollectionQueryAuthority.KeyringSecretRef = "QWQ_TEST_COLLECTION_AUTHORITY_KEYRING"
	t.Setenv(cfg.CollectionQueryAuthority.KeyringSecretRef, "not json")
	if err := registerCollectionQueryAuthority(nil, cfg, nil, nil, http.NewServeMux()); err == nil {
		t.Fatal("invalid keyring admitted")
	}
}
