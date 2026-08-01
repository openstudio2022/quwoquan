import Foundation

guard CommandLine.arguments.count == 2,
      let url = URL(string: CommandLine.arguments[1]) else {
  FileHandle.standardError.write(Data("usage: trust-probe <https-url>\n".utf8))
  exit(2)
}

let semaphore = DispatchSemaphore(value: 0)
var exitCode: Int32 = 1
let task = URLSession.shared.dataTask(with: url) { _, response, error in
  defer { semaphore.signal() }
  if let error {
    FileHandle.standardError.write(Data("system-trust probe failed: \(error)\n".utf8))
    return
  }
  guard let http = response as? HTTPURLResponse,
        (200..<500).contains(http.statusCode) else {
    FileHandle.standardError.write(Data("system-trust probe received no HTTP response\n".utf8))
    return
  }
  print("system-trust-ok status=\(http.statusCode)")
  exitCode = 0
}
task.resume()
if semaphore.wait(timeout: .now() + 20) == .timedOut {
  task.cancel()
  FileHandle.standardError.write(Data("system-trust probe timed out\n".utf8))
  exit(1)
}
exit(exitCode)
