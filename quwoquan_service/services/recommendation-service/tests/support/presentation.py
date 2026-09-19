"""对象级能力声明 builder；仅构造本测试需要的成员，不声明第二闭集。"""
from generated.recommendation.ranked_recommendation_window.models.client_presentation_contract import digest_client_content_presentation_contract

from generated.recommendation.ranked_recommendation_window.models.request_response import ClientContentPresentationContract
from internal.recommendation.ranked_recommendation_window.domain.model import post_envelope, homepage_envelope


def presentation_contract(**changes) -> ClientContentPresentationContract:
    values = {
        "contentTypes": ["image", "video", "article"],
        "listObjectKinds": ["post", "entity_homepage"],
        "presentationRecipes": ["cover_media_card", "article_excerpt_card", "homepage_summary_card"],
        "openSurfaces": ["media_immersive", "article_reader", "homepage_detail"],
    }
    values.update(changes)
    digest = digest_client_content_presentation_contract(values)
    return ClientContentPresentationContract(**values, contractDigest=digest)
