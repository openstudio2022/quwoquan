package reliabletask

import "errors"

var (
	ErrStoreRequired              = errors.New("reliabletask: store is required")
	ErrTaskNotFound               = errors.New("reliabletask: task not found")
	ErrNotificationNotFound       = errors.New("reliabletask: notification not found")
	ErrLeaseMismatch              = errors.New("reliabletask: lease token mismatch")
	ErrPayloadNotAllowed          = errors.New("reliabletask: payload contains keys outside allowlist")
	errNotificationPartialFailure = errors.New("reliabletask: notification has failed recipients")
)
