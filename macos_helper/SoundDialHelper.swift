// SoundDialHelper — native macOS per-app volume engine for SoundDial.
//
// Requires macOS 14.2+ (Core Audio process taps).
// Build:  swiftc -O -framework CoreAudio -framework AudioToolbox -framework AppKit \
//                -o SoundDialHelper SoundDialHelper.swift
//
// Protocol (JSON, one object per line):
//   stdin  -> {"cmd":"list"} | {"cmd":"set_volume","key":"com.spotify.client","volume":1.25}
//             {"cmd":"set_mute","key":"...","muted":true} | {"cmd":"set_master","volume":0.6,"muted":false}
//             {"cmd":"set_output","id":"<device uid>"} | {"cmd":"quit"}
//   stdout <- {"type":"state","apps":[{pid,bundle,name,volume,muted,peak,icon,active}],
//              "master":{"volume","muted"},"outputs":[{id,name,default}]}
//             {"type":"error","message":"..."} | {"type":"log","message":"..."}
//
// How it works: for every process that is outputting audio we create a Core Audio
// process tap with muteBehavior = .mutedWhenTapped (the app's own output is silenced),
// wrap the tap in a private aggregate device whose main sub-device is the current
// default output, and run an IO proc that copies the tapped samples to the output
// multiplied by the per-app gain (0.0 … 2.0). Mute == gain 0 without losing the slider.

import AppKit
import AudioToolbox
import CoreAudio
import Foundation

// MARK: - Small Core Audio helpers

func propAddress(_ sel: AudioObjectPropertySelector,
                 _ scope: AudioObjectPropertyScope = kAudioObjectPropertyScopeGlobal,
                 _ elem: AudioObjectPropertyElement = kAudioObjectPropertyElementMain) -> AudioObjectPropertyAddress {
    return AudioObjectPropertyAddress(mSelector: sel, mScope: scope, mElement: elem)
}

func getProp<T>(_ obj: AudioObjectID, _ addr: AudioObjectPropertyAddress, _ zero: T) -> T? {
    var a = addr
    var size = UInt32(MemoryLayout<T>.size)
    var value = zero
    let st = AudioObjectGetPropertyData(obj, &a, 0, nil, &size, &value)
    return st == noErr ? value : nil
}

func getPropArray<T: ExpressibleByIntegerLiteral>(_ obj: AudioObjectID, _ addr: AudioObjectPropertyAddress, _ type: T.Type) -> [T] {
    var a = addr
    var size: UInt32 = 0
    guard AudioObjectGetPropertyDataSize(obj, &a, 0, nil, &size) == noErr, size > 0 else { return [] }
    let count = Int(size) / MemoryLayout<T>.size
    var arr = [T](repeating: 0, count: count)
    let st = arr.withUnsafeMutableBytes { raw -> OSStatus in
        AudioObjectGetPropertyData(obj, &a, 0, nil, &size, raw.baseAddress!)
    }
    return st == noErr ? arr : []
}

func getString(_ obj: AudioObjectID, _ addr: AudioObjectPropertyAddress) -> String? {
    var a = addr
    var size = UInt32(MemoryLayout<CFString?>.size)
    var value: Unmanaged<CFString>?
    let st = withUnsafeMutablePointer(to: &value) { ptr -> OSStatus in
        AudioObjectGetPropertyData(obj, &a, 0, nil, &size, ptr)
    }
    guard st == noErr, let v = value else { return nil }
    return v.takeRetainedValue() as String
}

func setProp<T>(_ obj: AudioObjectID, _ addr: AudioObjectPropertyAddress, _ value: T) -> Bool {
    var a = addr
    var v = value
    return AudioObjectSetPropertyData(obj, &a, 0, nil, UInt32(MemoryLayout<T>.size), &v) == noErr
}

func hasProp(_ obj: AudioObjectID, _ addr: AudioObjectPropertyAddress) -> Bool {
    var a = addr
    return AudioObjectHasProperty(obj, &a)
}

func emit(_ obj: [String: Any]) {
    guard let data = try? JSONSerialization.data(withJSONObject: obj, options: []),
          let s = String(data: data, encoding: .utf8) else { return }
    FileHandle.standardOutput.write((s + "\n").data(using: .utf8)!)
}

func logLine(_ msg: String) { emit(["type": "log", "message": msg]) }
func errLine(_ msg: String) { emit(["type": "error", "message": msg]) }

// MARK: - Output devices

struct OutputDevice { let id: AudioObjectID; let uid: String; let name: String }

func defaultOutputDevice() -> AudioObjectID {
    return getProp(AudioObjectID(kAudioObjectSystemObject), propAddress(kAudioHardwarePropertyDefaultOutputDevice), AudioObjectID(0)) ?? 0
}

func outputDevices() -> [OutputDevice] {
    let ids = getPropArray(AudioObjectID(kAudioObjectSystemObject), propAddress(kAudioHardwarePropertyDevices), AudioObjectID.self)
    var out: [OutputDevice] = []
    for id in ids {
        var a = propAddress(kAudioDevicePropertyStreams, kAudioObjectPropertyScopeOutput)
        var size: UInt32 = 0
        guard AudioObjectGetPropertyDataSize(id, &a, 0, nil, &size) == noErr, size > 0 else { continue }
        guard let uid = getString(id, propAddress(kAudioDevicePropertyDeviceUID)) else { continue }
        // skip our own private aggregates and other aggregate devices
        if uid.hasPrefix("com.sounddial.") { continue }
        let name = getString(id, propAddress(kAudioObjectPropertyName)) ?? uid
        out.append(OutputDevice(id: id, uid: uid, name: name))
    }
    return out
}

func masterVolume(_ dev: AudioObjectID) -> (Float, Bool) {
    var vol: Float = 1.0
    if let v = getProp(dev, propAddress(kAudioDevicePropertyVolumeScalar, kAudioObjectPropertyScopeOutput, 0), Float(0)) {
        vol = v
    } else {
        let l = getProp(dev, propAddress(kAudioDevicePropertyVolumeScalar, kAudioObjectPropertyScopeOutput, 1), Float(0)) ?? 1
        let r = getProp(dev, propAddress(kAudioDevicePropertyVolumeScalar, kAudioObjectPropertyScopeOutput, 2), Float(0)) ?? l
        vol = max(l, r)
    }
    var muted = false
    if let m = getProp(dev, propAddress(kAudioDevicePropertyMute, kAudioObjectPropertyScopeOutput, 0), UInt32(0)) {
        muted = m != 0
    }
    return (vol, muted)
}

func setMasterVolume(_ dev: AudioObjectID, _ vol: Float?, _ muted: Bool?) {
    if let v = vol {
        if !setProp(dev, propAddress(kAudioDevicePropertyVolumeScalar, kAudioObjectPropertyScopeOutput, 0), v) {
            _ = setProp(dev, propAddress(kAudioDevicePropertyVolumeScalar, kAudioObjectPropertyScopeOutput, 1), v)
            _ = setProp(dev, propAddress(kAudioDevicePropertyVolumeScalar, kAudioObjectPropertyScopeOutput, 2), v)
        }
    }
    if let m = muted {
        if !setProp(dev, propAddress(kAudioDevicePropertyMute, kAudioObjectPropertyScopeOutput, 0), UInt32(m ? 1 : 0)) {
            _ = setProp(dev, propAddress(kAudioDevicePropertyMute, kAudioObjectPropertyScopeOutput, 1), UInt32(m ? 1 : 0))
            _ = setProp(dev, propAddress(kAudioDevicePropertyMute, kAudioObjectPropertyScopeOutput, 2), UInt32(m ? 1 : 0))
        }
    }
}

// MARK: - Process discovery

struct AudioProcess {
    let object: AudioObjectID
    let pid: pid_t
    let bundle: String
    let running: Bool
}

func audioProcesses() -> [AudioProcess] {
    let objs = getPropArray(AudioObjectID(kAudioObjectSystemObject), propAddress(kAudioHardwarePropertyProcessObjectList), AudioObjectID.self)
    var result: [AudioProcess] = []
    for o in objs {
        let pid = getProp(o, propAddress(kAudioProcessPropertyPID), pid_t(0)) ?? 0
        if pid <= 0 { continue }
        let bundle = getString(o, propAddress(kAudioProcessPropertyBundleID)) ?? ""
        let running = (getProp(o, propAddress(kAudioProcessPropertyIsRunningOutput), UInt32(0)) ?? 0) != 0
        result.append(AudioProcess(object: o, pid: pid, bundle: bundle, running: running))
    }
    return result
}

func appName(pid: pid_t, bundle: String) -> String {
    if let app = NSRunningApplication(processIdentifier: pid), let n = app.localizedName, !n.isEmpty { return n }
    if !bundle.isEmpty { return bundle.split(separator: ".").last.map(String.init) ?? bundle }
    return "PID \(pid)"
}

let iconDir: URL = {
    let d = FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask)[0].appendingPathComponent("SoundDial/icons")
    try? FileManager.default.createDirectory(at: d, withIntermediateDirectories: true)
    return d
}()
var iconCache: [String: String] = [:]

func iconPath(pid: pid_t, key: String) -> String? {
    if let p = iconCache[key] { return p }
    guard let app = NSRunningApplication(processIdentifier: pid), let url = app.bundleURL else { return nil }
    let img = NSWorkspace.shared.icon(forFile: url.path)
    img.size = NSSize(width: 64, height: 64)
    guard let tiff = img.tiffRepresentation, let rep = NSBitmapImageRep(data: tiff),
          let png = rep.representation(using: .png, properties: [:]) else { return nil }
    let safe = key.replacingOccurrences(of: "/", with: "_")
    let file = iconDir.appendingPathComponent(safe + ".png")
    try? png.write(to: file)
    iconCache[key] = file.path
    return file.path
}

// MARK: - Per-process tap

final class AppTap {
    let key: String
    let pid: pid_t
    let processObject: AudioObjectID
    var tapID: AudioObjectID = 0
    var aggID: AudioObjectID = 0
    var procID: AudioDeviceIOProcID?
    var gain: Float = 1.0          // 0 … 2
    var muted = false
    var peak: Float = 0            // written from the IO thread (benign race for a meter)
    var lastSeen = Date()
    var started = false
    let tapUUID = UUID()

    init(key: String, pid: pid_t, object: AudioObjectID) {
        self.key = key; self.pid = pid; self.processObject = object
    }

    func start(outputUID: String) -> Bool {
        let desc = CATapDescription(stereoMixdownOfProcesses: [processObject])
        desc.uuid = tapUUID
        desc.name = "SoundDial \(key)"
        desc.muteBehavior = .mutedWhenTapped
        desc.isPrivate = true
        var tid: AudioObjectID = 0
        var st = AudioHardwareCreateProcessTap(desc, &tid)
        guard st == noErr else { errLine("tap create failed for \(key): \(st) — check System Settings › Privacy & Security › Screen & System Audio Recording"); return false }
        tapID = tid

        let aggDesc: [String: Any] = [
            kAudioAggregateDeviceNameKey as String: "SoundDial \(key)",
            kAudioAggregateDeviceUIDKey as String: "com.sounddial.agg.\(tapUUID.uuidString)",
            kAudioAggregateDeviceMainSubDeviceKey as String: outputUID,
            kAudioAggregateDeviceIsPrivateKey as String: true,
            kAudioAggregateDeviceIsStackedKey as String: false,
            kAudioAggregateDeviceTapAutoStartKey as String: true,
            kAudioAggregateDeviceSubDeviceListKey as String: [[kAudioSubDeviceUIDKey as String: outputUID]],
            kAudioAggregateDeviceTapListKey as String: [[
                kAudioSubTapUIDKey as String: tapUUID.uuidString,
                kAudioSubTapDriftCompensationKey as String: true,
            ]],
        ]
        var aid: AudioObjectID = 0
        st = AudioHardwareCreateAggregateDevice(aggDesc as CFDictionary, &aid)
        guard st == noErr else { errLine("aggregate create failed for \(key): \(st)"); AudioHardwareDestroyProcessTap(tapID); tapID = 0; return false }
        aggID = aid

        let queue = DispatchQueue(label: "sounddial.io.\(key)", qos: .userInteractive)
        var pid: AudioDeviceIOProcID?
        st = AudioDeviceCreateIOProcIDWithBlock(&pid, aggID, queue) { [weak self] _, inData, _, outData, _ in
            guard let self = self else { return }
            self.process(inData, outData)
        }
        guard st == noErr, let p = pid else { errLine("ioproc create failed for \(key): \(st)"); stop(); return false }
        procID = p
        st = AudioDeviceStart(aggID, procID)
        guard st == noErr else { errLine("device start failed for \(key): \(st)"); stop(); return false }
        started = true
        return true
    }

    /// Copy tapped input to the output at `gain`. Handles channel-count mismatches.
    @inline(__always)
    private func process(_ inData: UnsafePointer<AudioBufferList>, _ outData: UnsafeMutablePointer<AudioBufferList>) {
        let inList = UnsafeMutableAudioBufferListPointer(UnsafeMutablePointer(mutating: inData))
        let outList = UnsafeMutableAudioBufferListPointer(outData)
        let g: Float = muted ? 0 : gain
        var pk: Float = 0
        let nIn = inList.count
        for (j, ob) in outList.enumerated() {
            guard let oPtr = ob.mData?.assumingMemoryBound(to: Float.self) else { continue }
            let oCh = Int(ob.mNumberChannels)
            let oFrames = Int(ob.mDataByteSize) / (4 * max(1, oCh))
            if nIn == 0 || g == 0 {
                memset(ob.mData, 0, Int(ob.mDataByteSize))
                continue
            }
            let ib = inList[min(j, nIn - 1)]
            guard let iPtr = ib.mData?.assumingMemoryBound(to: Float.self) else { memset(ob.mData, 0, Int(ob.mDataByteSize)); continue }
            let iCh = Int(ib.mNumberChannels)
            let iFrames = Int(ib.mDataByteSize) / (4 * max(1, iCh))
            let frames = min(oFrames, iFrames)
            if oCh == iCh {
                let n = frames * oCh
                var i = 0
                while i < n {
                    let v = iPtr[i] * g
                    oPtr[i] = v
                    let a = abs(v); if a > pk { pk = a }
                    i += 1
                }
            } else {
                for f in 0..<frames {
                    for c in 0..<oCh {
                        let v = iPtr[f * iCh + min(c, iCh - 1)] * g
                        oPtr[f * oCh + c] = v
                        let a = abs(v); if a > pk { pk = a }
                    }
                }
            }
            if frames < oFrames {
                memset(oPtr + frames * oCh, 0, (oFrames - frames) * oCh * 4)
            }
        }
        // meter: fast attack, slow release
        peak = pk > peak ? pk : peak * 0.85
    }

    func stop() {
        if started, let p = procID { AudioDeviceStop(aggID, p) }
        if let p = procID { AudioDeviceDestroyIOProcID(aggID, p); procID = nil }
        if aggID != 0 { AudioHardwareDestroyAggregateDevice(aggID); aggID = 0 }
        if tapID != 0 { AudioHardwareDestroyProcessTap(tapID); tapID = 0 }
        started = false
    }

    deinit { stop() }
}

// MARK: - Engine

final class Engine {
    var taps: [String: AppTap] = [:]
    var desired: [String: (gain: Float, muted: Bool)] = [:]   // remembered within this helper's life
    var outputUID: String = ""
    var outputID: AudioObjectID = 0
    var mutedByUs = false

    init() {
        refreshOutput()
        // follow default-output changes
        var addr = propAddress(kAudioHardwarePropertyDefaultOutputDevice)
        AudioObjectAddPropertyListenerBlock(AudioObjectID(kAudioObjectSystemObject), &addr, DispatchQueue.main) { [weak self] _, _ in
            self?.outputChanged()
        }
    }

    func refreshOutput() {
        outputID = defaultOutputDevice()
        outputUID = getString(outputID, propAddress(kAudioDevicePropertyDeviceUID)) ?? ""
    }

    func outputChanged() {
        let old = outputUID
        refreshOutput()
        guard old != outputUID else { return }
        logLine("default output changed → \(outputUID); rebuilding taps")
        let keys = Array(taps.keys)
        for k in keys { taps[k]?.stop(); taps.removeValue(forKey: k) }
        poll()
    }

    func keyFor(_ p: AudioProcess) -> String {
        return p.bundle.isEmpty ? "pid:\(p.pid)" : p.bundle
    }

    /// Discover processes, create taps for new audible ones, drop vanished ones.
    func poll() {
        let procs = audioProcesses()
        var seen = Set<String>()
        for p in procs {
            // skip ourselves and the parent SoundDial process
            if p.pid == getpid() || p.pid == getppid() { continue }
            let key = keyFor(p)
            if p.running {
                seen.insert(key)
                if let t = taps[key] {
                    t.lastSeen = Date()
                } else if !outputUID.isEmpty {
                    let t = AppTap(key: key, pid: p.pid, object: p.object)
                    if let d = desired[key] { t.gain = d.gain; t.muted = d.muted }
                    if t.start(outputUID: outputUID) {
                        taps[key] = t
                    }
                }
            } else if let t = taps[key] {
                // process alive but silent for a while: keep the tap 20 s, then release
                if Date().timeIntervalSince(t.lastSeen) < 20 { seen.insert(key) }
            }
        }
        for (k, t) in taps where !seen.contains(k) {
            t.stop()
            taps.removeValue(forKey: k)
        }
    }

    func state() -> [String: Any] {
        var apps: [[String: Any]] = []
        let procs = audioProcesses()
        for p in procs {
            if p.pid == getpid() || p.pid == getppid() { continue }
            let key = keyFor(p)
            guard let t = taps[key] else { continue }
            apps.append([
                "pid": Int(p.pid), "bundle": key, "name": appName(pid: p.pid, bundle: p.bundle),
                "volume": Double(t.gain), "muted": t.muted, "peak": Double(t.peak),
                "icon": iconPath(pid: p.pid, key: key) ?? NSNull(), "active": p.running,
            ])
        }
        let (mv, mm) = masterVolume(outputID)
        let outs = outputDevices().map { ["id": $0.uid, "name": $0.name, "default": $0.uid == outputUID] as [String: Any] }
        return ["type": "state", "apps": apps, "master": ["volume": Double(mv), "muted": mm], "outputs": outs]
    }

    func handle(_ msg: [String: Any]) {
        guard let cmd = msg["cmd"] as? String else { return }
        switch cmd {
        case "list":
            poll(); emit(state())
        case "set_volume":
            if let k = msg["key"] as? String, let v = msg["volume"] as? Double {
                let g = Float(max(0, min(2, v)))
                taps[k]?.gain = g
                desired[k] = (g, desired[k]?.muted ?? taps[k]?.muted ?? false)
            }
            emit(state())
        case "set_mute":
            if let k = msg["key"] as? String, let m = msg["muted"] as? Bool {
                taps[k]?.muted = m
                desired[k] = (desired[k]?.gain ?? taps[k]?.gain ?? 1, m)
            }
            emit(state())
        case "set_master":
            let v = (msg["volume"] as? Double).map { Float($0) }
            let m = msg["muted"] as? Bool
            setMasterVolume(outputID, v, m)
            emit(state())
        case "set_output":
            if let uid = msg["id"] as? String, let dev = outputDevices().first(where: { $0.uid == uid }) {
                if !setProp(AudioObjectID(kAudioObjectSystemObject), propAddress(kAudioHardwarePropertyDefaultOutputDevice), dev.id) {
                    errLine("could not set default output")
                }
            }
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) { emit(self.state()) }
        case "quit":
            shutdown()
        default:
            errLine("unknown cmd \(cmd)")
        }
    }

    func shutdown() {
        for (_, t) in taps { t.stop() }
        taps.removeAll()
        exit(0)
    }
}

// MARK: - Main

if #available(macOS 14.2, *) {
    let engine = Engine()
    signal(SIGINT) { _ in exit(0) }
    signal(SIGTERM) { _ in exit(0) }
    signal(SIGPIPE) { _ in exit(0) }

    // stdin reader
    let reader = Thread {
        while let line = readLine(strippingNewline: true) {
            guard let data = line.data(using: .utf8),
                  let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else { continue }
            DispatchQueue.main.async { engine.handle(obj) }
        }
        DispatchQueue.main.async { engine.shutdown() }   // parent closed the pipe
    }
    reader.start()

    // periodic discovery + state push (keeps meters/badges live without the UI asking)
    let timer = Timer(timeInterval: 0.5, repeats: true) { _ in
        engine.poll()
        emit(engine.state())
    }
    RunLoop.main.add(timer, forMode: .common)
    logLine("SoundDialHelper ready; output=\(engine.outputUID)")
    RunLoop.main.run()
} else {
    errLine("SoundDialHelper needs macOS 14.2 or newer")
    exit(2)
}
