import Foundation

// 与 launch metadata 的 Python sort_keys / UTF-8 / 紧凑 JSON 字节保持一致。
// Foundation sortedKeys 使用本地化及数字排序，不能作为签名和摘要输入。
enum NativeRuntimeCanonicalJSON {
  static func data(_ value: Any) throws -> Data {
    if let object = value as? [String: Any] {
      let entries = object.sorted { $0.key.utf8.lexicographicallyPrecedes($1.key.utf8) }
      var result = Data("{".utf8)
      for (index, entry) in entries.enumerated() {
        if index > 0 { result.append(contentsOf: ",".utf8) }
        result.append(try data(entry.key))
        result.append(contentsOf: ":".utf8)
        result.append(try data(entry.value))
      }
      result.append(contentsOf: "}".utf8)
      return result
    }
    if let array = value as? [Any] {
      var result = Data("[".utf8)
      for (index, item) in array.enumerated() {
        if index > 0 { result.append(contentsOf: ",".utf8) }
        result.append(try data(item))
      }
      result.append(contentsOf: "]".utf8)
      return result
    }
    return try JSONSerialization.data(
      withJSONObject: value,
      options: [.fragmentsAllowed, .withoutEscapingSlashes]
    )
  }
}
