package application

import "net/http"

// OperationAdmissionPort evaluates one request against the generated
// ContractGraph operation descriptors before shared admission.
type OperationAdmissionPort interface {
	Wrap(http.Handler) http.Handler
}

// Facade keeps the api-edge composition root dependent on this object's typed
// port instead of the shared runtime/auth implementation.
type Facade struct {
	port OperationAdmissionPort
}

func NewFacade(port OperationAdmissionPort) *Facade {
	if port == nil {
		panic("operation admission port is required")
	}
	return &Facade{port: port}
}

func (facade *Facade) Wrap(next http.Handler) http.Handler {
	if facade == nil || facade.port == nil {
		panic("operation admission facade is not configured")
	}
	if next == nil {
		panic("operation admission next handler is required")
	}
	return facade.port.Wrap(next)
}
