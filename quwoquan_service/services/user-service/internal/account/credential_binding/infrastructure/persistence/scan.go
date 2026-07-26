package persistence

import (
	"errors"
	"fmt"

	"github.com/jackc/pgx/v5"

	bindingmodel "quwoquan_service/services/user-service/internal/account/credential_binding/domain/model"
)

type rowScanner interface {
	Scan(...any) error
}

func scanCredentialBinding(
	row rowScanner,
) (bindingmodel.CredentialBinding, bool, error) {
	var (
		state   bindingmodel.State
		rawType string
		active  bool
	)
	err := row.Scan(
		&state.ID,
		&state.OwnerID,
		&rawType,
		&state.CredentialKey,
		&state.DisplayLabel,
		&active,
		&state.BoundAt,
		&state.LastUsedAt,
		&state.Version,
	)
	if errors.Is(err, pgx.ErrNoRows) {
		return bindingmodel.CredentialBinding{}, false, nil
	}
	if err != nil {
		return bindingmodel.CredentialBinding{}, false, fmt.Errorf(
			"scan CredentialBinding row: %w",
			err,
		)
	}
	state.CredentialType = bindingmodel.CredentialType(rawType)
	state.Status = bindingmodel.StatusRevoked
	if active {
		state.Status = bindingmodel.StatusActive
	}
	binding, err := bindingmodel.Restore(state)
	if err != nil {
		return bindingmodel.CredentialBinding{}, false, fmt.Errorf(
			"restore CredentialBinding row: %w",
			err,
		)
	}
	return binding, true, nil
}

const credentialBindingSelectColumns = `
id,
owner_id,
credential_type,
credential_key,
COALESCE(display_label, ''),
is_active,
bound_at,
last_used_at,
version`
