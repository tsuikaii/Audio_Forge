import AppKit
import QuartzCore

// Use Core Animation's continuous corner curve for the macOS app tile,
// while retaining the original pixel artwork inside the rounded mask.
let destination = CommandLine.arguments[1]
let sizes = [(16,1),(16,2),(32,1),(32,2),(128,1),(128,2),(256,1),(256,2),(512,1),(512,2)]
func bitmap(_ pixels: Int) -> NSBitmapImageRep {
    NSBitmapImageRep(bitmapDataPlanes:nil, pixelsWide:pixels, pixelsHigh:pixels, bitsPerSample:8, samplesPerPixel:4, hasAlpha:true, isPlanar:false, colorSpaceName:.deviceRGB, bytesPerRow:0, bitsPerPixel:0)!
}
for (size,scale) in sizes {
    let pixels = size * scale
    let artwork = bitmap(pixels)
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep:artwork)
    let unit = CGFloat(pixels)/32
    func rect(_ x:CGFloat,_ y:CGFloat,_ w:CGFloat,_ h:CGFloat,_ color:NSColor) {
        color.setFill(); NSBezierPath(rect:NSRect(x:x*unit,y:(32-y-h)*unit,width:w*unit,height:h*unit)).fill()
    }
    rect(0,0,32,32,NSColor(calibratedWhite:0.75,alpha:1))
    rect(3,3,26,6,NSColor(calibratedRed:0,green:0,blue:0.5,alpha:1)); rect(5,5,2,2,.white)
    rect(6,15,5,8,.black); rect(7,16,4,6,.white)
    rect(11,14,2,10,.black); rect(13,12,2,14,.black); rect(15,11,3,16,.black)
    rect(11,16,2,6,.white); rect(13,14,2,10,.white); rect(15,13,1,12,.white)
    rect(20,13,2,3,.black); rect(22,16,2,7,.black); rect(20,23,2,3,.black)
    rect(24,11,2,3,.black); rect(26,14,1,11,.black); rect(24,25,2,3,.black)
    rect(19,12,2,3,.yellow); rect(21,15,2,7,.yellow); rect(19,22,2,3,.yellow)
    rect(23,10,2,3,.yellow); rect(25,13,1,11,.yellow); rect(23,24,2,3,.yellow)
    NSGraphicsContext.restoreGraphicsState()

    let result = bitmap(pixels)
    let canvas = CALayer()
    canvas.frame = CGRect(x:0,y:0,width:pixels,height:pixels)
    let tile = CALayer()
    tile.frame = CGRect(x:2*unit,y:2*unit,width:28*unit,height:28*unit)
    tile.contents = artwork.cgImage
    tile.contentsGravity = .resize
    tile.contentsScale = CGFloat(scale)
    tile.magnificationFilter = .nearest
    tile.cornerCurve = .continuous
    tile.cornerRadius = 28*unit*0.223
    tile.masksToBounds = true
    tile.borderWidth = 0.35*unit
    tile.borderColor = NSColor(calibratedWhite:0.35,alpha:0.6).cgColor
    canvas.addSublayer(tile)
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep:result)
    canvas.render(in:NSGraphicsContext.current!.cgContext)
    NSGraphicsContext.restoreGraphicsState()
    let data = result.representation(using:.png,properties:[:])!
    let name = "icon_\(size)x\(size)" + (scale == 2 ? "@2x" : "") + ".png"
    try data.write(to:URL(fileURLWithPath:destination).appendingPathComponent(name))
}
