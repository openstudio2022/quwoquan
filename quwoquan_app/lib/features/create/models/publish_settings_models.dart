class CreateLocationOption {
  const CreateLocationOption({
    required this.name,
    required this.latitude,
    required this.longitude,
    this.address = '',
    this.distanceMeters,
  });

  final String name;
  final double latitude;
  final double longitude;
  final String address;
  final int? distanceMeters;

  static const CreateLocationOption hidden = CreateLocationOption(
    name: '',
    latitude: 0,
    longitude: 0,
  );

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
