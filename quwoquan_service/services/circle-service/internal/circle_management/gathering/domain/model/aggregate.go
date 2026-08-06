package gathering

import (
	"errors"

	contract "quwoquan_service/services/circle-service/generated/circle_management/gathering/contract/model"
)

// Gathering is the canonical generated aggregate. Domain behavior is split
// across lifecycle, participation, attendance, host, and outcome files.
type Gathering = contract.Gathering

var ErrInvalidArgument = errors.New("invalid Gathering argument")
