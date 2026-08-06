enum CallLayoutMode {
  grid,
  speaker;

  bool get isGrid => this == CallLayoutMode.grid;
  bool get isSpeaker => this == CallLayoutMode.speaker;

  CallLayoutMode toggle() {
    return this == CallLayoutMode.grid
        ? CallLayoutMode.speaker
        : CallLayoutMode.grid;
  }
}
