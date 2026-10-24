import AVFoundation
import AppKit

let a = CommandLine.arguments
guard a.count == 5, let fps = Int32(a[3]), let bitrate = Int(a[4]) else {
    FileHandle.standardError.write("usage: frames2mp4 <frames-dir> <out.mp4> <fps> <bitrate>\n".data(using: .utf8)!)
    exit(2)
}
let dir = a[1], out = a[2]
let files = try FileManager.default.contentsOfDirectory(atPath: dir).filter { $0.hasSuffix(".png") }.sorted()

func load(_ name: String) -> CGImage {
    guard let img = NSImage(contentsOfFile: dir + "/" + name),
          let cg = img.cgImage(forProposedRect: nil, context: nil, hints: nil) else { fatalError("cannot read \(name)") }
    return cg
}
let first = load(files[0])
let w = first.width, h = first.height

try? FileManager.default.removeItem(atPath: out)
let writer = try AVAssetWriter(outputURL: URL(fileURLWithPath: out), fileType: .mp4)
let input = AVAssetWriterInput(mediaType: .video, outputSettings: [
    AVVideoCodecKey: AVVideoCodecType.h264, AVVideoWidthKey: w, AVVideoHeightKey: h,
    AVVideoCompressionPropertiesKey: [
        AVVideoAverageBitRateKey: bitrate,
        AVVideoProfileLevelKey: AVVideoProfileLevelH264HighAutoLevel,
        AVVideoMaxKeyFrameIntervalKey: Int(fps) * 2,
    ],
])
let adaptor = AVAssetWriterInputPixelBufferAdaptor(assetWriterInput: input, sourcePixelBufferAttributes: [
    kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_32ARGB,
    kCVPixelBufferWidthKey as String: w, kCVPixelBufferHeightKey as String: h,
])
writer.add(input)
writer.startWriting()
writer.startSession(atSourceTime: .zero)

let space = CGColorSpace(name: CGColorSpace.sRGB)!
for (i, name) in files.enumerated() {
    while !input.isReadyForMoreMediaData { Thread.sleep(forTimeInterval: 0.002) }
    var pb: CVPixelBuffer?
    CVPixelBufferPoolCreatePixelBuffer(nil, adaptor.pixelBufferPool!, &pb)
    let buf = pb!
    CVPixelBufferLockBaseAddress(buf, [])
    let ctx = CGContext(data: CVPixelBufferGetBaseAddress(buf), width: w, height: h, bitsPerComponent: 8,
                        bytesPerRow: CVPixelBufferGetBytesPerRow(buf), space: space,
                        bitmapInfo: CGImageAlphaInfo.noneSkipFirst.rawValue)!
    ctx.draw(load(name), in: CGRect(x: 0, y: 0, width: w, height: h))
    CVPixelBufferUnlockBaseAddress(buf, [])
    adaptor.append(buf, withPresentationTime: CMTime(value: Int64(i), timescale: fps))
}
input.markAsFinished()
let done = DispatchSemaphore(value: 0)
writer.finishWriting { done.signal() }
done.wait()
print("\(files.count) frames -> \(out) [\(writer.status == .completed ? "ok" : "failed: \(String(describing: writer.error))")]")
