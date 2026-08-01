package application

// SearchFeedbackCommandFacade is the object-owned application entry for
// SearchFeedbackFact append commands declared in contracts/search/search_feedback_fact.
//
// HTTP and persistence currently compose through search_query; this package
// anchors ownership so api_routes and application source stay co-located.
type SearchFeedbackCommandFacade struct{}
