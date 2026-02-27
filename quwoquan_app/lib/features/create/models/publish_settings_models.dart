class CreateLocationOption {
  const CreateLocationOption({
    required this.name,
    required this.latitude,
    required this.longitude,
  });

  final String name;
  final double latitude;
  final double longitude;

  Map<String, dynamic> toLocationMap() => <String, dynamic>{
    'latitude': latitude,
    'longitude': longitude,
  };
}

class CreateCircleOption {
  const CreateCircleOption({required this.id, required this.name});

  final String id;
  final String name;
}
