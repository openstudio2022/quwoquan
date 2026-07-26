package model // TagNodeView and its object-owned index aliases

import (
	indexcontract "quwoquan_service/services/tag-service/generated/tag/object_tag_index_view/contract/tag"
	nodecontract "quwoquan_service/services/tag-service/generated/tag/tag_node_view/contract/tag"
)

type TagNode = nodecontract.TagNodeView
type ObjectTagIndex = indexcontract.ObjectTagIndex
