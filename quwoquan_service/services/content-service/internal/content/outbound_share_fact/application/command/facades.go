package command

import "context"

type Facades struct {
	OutboundShareAppendFacet
}

type OutboundShareAppendFacet interface {
	AppendOutboundShare(context.Context, AppendOutboundShareCommand) (AppendOutboundShareResult, error)
}

func BindFacades(service *Service) *Facades {
	if service == nil {
		return nil
	}
	return &Facades{OutboundShareAppendFacet: service}
}
