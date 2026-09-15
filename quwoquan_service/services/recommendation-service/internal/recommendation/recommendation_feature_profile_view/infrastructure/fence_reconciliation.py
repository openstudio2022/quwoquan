"""Feature owner独立持久消费依据，不访问Candidate私有集合。"""
from pymongo.errors import DuplicateKeyError


class FeatureFenceReceipts:
    def __init__(self, database):
        self.collection = database["recommendation_feature_content_fence_receipts"]
        self.collection.create_index([("eventDigest", 1)], unique=True, name="uq_rec_feature_fence_event")
        self.collection.create_index([("scopeDigest", 1), ("revision", 1)], unique=True, name="uq_rec_feature_fence_revision")

    def find(self, key):
        return self.collection.find_one({"eventDigest": key})

    def save(self, receipt):
        try:
            self.collection.insert_one(receipt)
        except DuplicateKeyError:
            old = self.find(receipt["eventDigest"])
            if old is None or old["payloadDigest"] != receipt["payloadDigest"]:
                raise ValueError("Content fence revision conflict")
