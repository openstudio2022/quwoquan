package application

import "net"

type NetworkAttributes struct {
	Region  string
	Carrier string
}

// NetworkAttributeResolver derives rollout attributes only from the trusted
// source address supplied by the edge proxy. It must not perform online lookups.
type NetworkAttributeResolver interface {
	Resolve(net.IP) NetworkAttributes
}
