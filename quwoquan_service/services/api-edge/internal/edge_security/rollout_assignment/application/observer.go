package application

// DecisionObservation contains only bounded operational dimensions. Installation
// identities, source addresses and subject digests must never cross this boundary.
type DecisionObservation struct {
	Stage      string
	Target     string
	Platform   string
	AppVersion string
	AppBuild   string
	Region     string
	Carrier    string
	Reason     string
}

type Observer interface {
	ObserveDecision(DecisionObservation)
}
