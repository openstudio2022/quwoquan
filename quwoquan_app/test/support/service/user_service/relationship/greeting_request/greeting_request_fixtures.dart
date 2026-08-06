Map<String, Object?> greetingRequestRecordFixture({required String status}) {
  return <String, Object?>{
    'id': 'greeting-1',
    'requesterPersonaId': 'persona-current',
    'targetPersonaId': 'persona-target',
    'requestMessage': '你好',
    'status': status,
    'source': 'profile',
    'createdAt': '2026-07-20T00:00:00Z',
    'updatedAt': '2026-07-20T00:00:00Z',
  };
}
