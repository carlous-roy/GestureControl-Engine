// GestureControl demo — browser-based hand tracking with MediaPipe.
// The finger rules, the One Euro filter and the 3-frame confirmation are the
// same code path as the Python engine (src/gesture/, checked against the
// shared golden vectors in test/golden_vectors.json); only the relays are
// simulated in the page.
import { useState, useEffect, useRef } from "react";
import { GesturePipeline, DEFAULT_RULES } from "./gesture/pipeline.js";

/**
 * The @mediapipe/* packages ship UMD bundles that assign to `window` rather
 * than exposing real ES named exports. Vite's production build turns the
 * named destructure into `undefined`, which showed up at runtime as
 * "C is not a constructor" (C being the minified `Hands`).
 *
 * Resolve from the module when that works, and otherwise load the UMD build
 * from the CDN and read the globals.
 */
const MP_CDN = "https://cdn.jsdelivr.net/npm";

function loadScript(src) {
  return new Promise((resolve, reject) => {
    if (document.querySelector(`script[data-mp="${src}"]`)) return resolve();
    const el = document.createElement("script");
    el.src = src;
    el.dataset.mp = src;
    el.onload = () => resolve();
    el.onerror = () => reject(new Error("Failed to load " + src));
    document.head.appendChild(el);
  });
}

function pickExport(mod, name) {
  const fromModule = mod?.[name] ?? mod?.default?.[name];
  if (fromModule !== undefined && fromModule !== null) return fromModule;
  return window[name];
}

async function loadMediaPipe() {
  let Hands, Camera, drawConnectors, drawLandmarks, HAND_CONNECTIONS;

  try {
    const handsMod = await import("@mediapipe/hands");
    const cameraMod = await import("@mediapipe/camera_utils");
    const drawMod = await import("@mediapipe/drawing_utils");
    Hands = pickExport(handsMod, "Hands");
    HAND_CONNECTIONS = pickExport(handsMod, "HAND_CONNECTIONS");
    Camera = pickExport(cameraMod, "Camera");
    drawConnectors = pickExport(drawMod, "drawConnectors");
    drawLandmarks = pickExport(drawMod, "drawLandmarks");
  } catch {
    // fall through to the CDN path
  }

  if (typeof Hands !== "function" || typeof Camera !== "function") {
    await loadScript(`${MP_CDN}/@mediapipe/hands/hands.js`);
    await loadScript(`${MP_CDN}/@mediapipe/camera_utils/camera_utils.js`);
    await loadScript(`${MP_CDN}/@mediapipe/drawing_utils/drawing_utils.js`);
    Hands = window.Hands;
    Camera = window.Camera;
    drawConnectors = window.drawConnectors;
    drawLandmarks = window.drawLandmarks;
    HAND_CONNECTIONS = window.HAND_CONNECTIONS;
  }

  if (typeof Hands !== "function")
    throw new Error("MediaPipe Hands failed to load from both the bundle and the CDN");
  if (typeof Camera !== "function")
    throw new Error("MediaPipe Camera failed to load from both the bundle and the CDN");

  return { Hands, Camera, drawConnectors, drawLandmarks, HAND_CONNECTIONS };
}


const GESTURE_MAP = [
  { fingers: 0, label: "Fist", action: "All OFF" },
  { fingers: 1, label: "Index Finger", action: "Relay 1 ON" },
  { fingers: 2, label: "Peace Sign", action: "Relay 2 ON" },
  { fingers: 3, label: "Three Fingers", action: "Relay 3 ON" },
  { fingers: 4, label: "Four Fingers", action: "Relay 4 ON" },
  { fingers: 5, label: "Open Hand", action: "All ON" },
];

const TECH_STACK = [
  { name: "Python 3", role: "Runtime", color: "#3776AB" },
  { name: "OpenCV", role: "Camera & Video", color: "#5C3EE8" },
  { name: "MediaPipe", role: "Hand Tracking", color: "#0F9D58" },
  { name: "pyFirmata2", role: "Arduino Protocol", color: "#00979D" },
  { name: "Arduino UNO", role: "Microcontroller", color: "#00979D" },
  { name: "4-Ch Relay", role: "Appliance Switching", color: "#DC2626" },
];

const CONFIRM_FRAMES = DEFAULT_RULES.confirm_frames;


function useHandTracking(videoRef, canvasRef, isActive) {
  const [confirmedCount, setConfirmedCount] = useState(-1);
  const [liveCount, setLiveCount] = useState(-1);
  const [runLength, setRunLength] = useState(0);
  const [fps, setFps] = useState(0);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);
  const handsRef = useRef(null);
  const cameraRef = useRef(null);
  const pipelineRef = useRef(null);
  const frameCountRef = useRef(0);
  const lastTimeRef = useRef(performance.now());

  useEffect(() => {
    if (!isActive) {
      if (cameraRef.current) { cameraRef.current.stop(); cameraRef.current = null; }
      if (handsRef.current) { handsRef.current.close(); handsRef.current = null; }
      pipelineRef.current = null;
      setConfirmedCount(-1);
      setLiveCount(-1);
      setRunLength(0);
      setIsLoading(true);
      setError(null);
      return;
    }

    let cancelled = false;

    async function initMediaPipe() {
      try {
        setIsLoading(true);
        setError(null);

        const { Hands, Camera, drawConnectors, drawLandmarks, HAND_CONNECTIONS } =
          await loadMediaPipe();

        if (cancelled) return;

        const hands = new Hands({
          locateFile: (file) => `https://cdn.jsdelivr.net/npm/@mediapipe/hands/${file}`,
        });

        hands.setOptions({
          maxNumHands: 1,
          modelComplexity: 1,
          minDetectionConfidence: 0.7,
          minTrackingConfidence: 0.6,
        });

        hands.onResults((results) => {
          if (cancelled) return;
          const canvas = canvasRef.current;
          if (!canvas) return;
          const ctx = canvas.getContext("2d");
          canvas.width = results.image.width;
          canvas.height = results.image.height;
          if (!pipelineRef.current || pipelineRef.current.width !== canvas.width || pipelineRef.current.height !== canvas.height) {
            pipelineRef.current = new GesturePipeline(canvas.width, canvas.height);
          }

          ctx.save();
          ctx.clearRect(0, 0, canvas.width, canvas.height);
          ctx.drawImage(results.image, 0, 0, canvas.width, canvas.height);

          const hand = results.multiHandLandmarks && results.multiHandLandmarks.length > 0
            ? results.multiHandLandmarks[0].map((p) => [p.x, p.y])
            : null;
          // Same pipeline as the engine: One Euro filter, hand-frame rules with
          // hysteresis, then a count must hold for CONFIRM_FRAMES frames.
          const result = pipelineRef.current.process(hand, performance.now() / 1000);

          if (result.pointsPx) {
            const filtered = result.pointsPx.map(([x, y]) => ({ x: x / canvas.width, y: y / canvas.height }));
            drawConnectors(ctx, filtered, HAND_CONNECTIONS, {
              color: "rgba(220, 38, 38, 0.6)", lineWidth: 2,
            });
            drawLandmarks(ctx, filtered, {
              color: "#DC2626", lineWidth: 1, radius: 3,
            });
          }

          setLiveCount(result.rawCount);
          setConfirmedCount(result.confirmedCount);
          setRunLength(hand ? pipelineRef.current.stabilizer.run : 0);

          ctx.restore();

          // FPS
          frameCountRef.current++;
          const now = performance.now();
          if (now - lastTimeRef.current >= 1000) {
            setFps(Math.round(frameCountRef.current * 1000 / (now - lastTimeRef.current)));
            frameCountRef.current = 0;
            lastTimeRef.current = now;
          }
        });

        handsRef.current = hands;
        if (!videoRef.current || cancelled) return;

        const camera = new Camera(videoRef.current, {
          onFrame: async () => {
            if (handsRef.current && videoRef.current) {
              await handsRef.current.send({ image: videoRef.current });
            }
          },
          width: 640, height: 480,
        });

        cameraRef.current = camera;
        await camera.start();
        if (!cancelled) setIsLoading(false);
      } catch (err) {
        if (!cancelled) {
          const CAM_ERRORS = {
            NotAllowedError: "Camera access denied. Allow camera for this site, and check System Settings > Privacy & Security > Camera for your browser.",
            NotFoundError: "No camera was found on this device.",
            NotReadableError: "The camera is in use by another app. Quit Zoom, Teams or Photo Booth and try again.",
            OverconstrainedError: "This camera cannot provide the 640x480 feed the demo requests.",
            SecurityError: "The browser blocked camera access on this page.",
            AbortError: "Camera startup was interrupted. Try again.",
          };
          setError(
            (CAM_ERRORS[err.name] || "Could not start hand tracking.") +
            " [" + err.name + ": " + err.message + "]"
          );
          setIsLoading(false);
        }
      }
    }

    initMediaPipe();
    return () => {
      cancelled = true;
      if (cameraRef.current) { cameraRef.current.stop(); cameraRef.current = null; }
      if (handsRef.current) { handsRef.current.close(); handsRef.current = null; }
    };
  }, [isActive, videoRef, canvasRef]);

  return { confirmedCount, liveCount, runLength, fps, isLoading, error };
}


export default function App() {
  const [demoActive, setDemoActive] = useState(false);
  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const { confirmedCount, liveCount, runLength, fps, isLoading, error } = useHandTracking(videoRef, canvasRef, demoActive);

  // The relay panel follows the confirmed count through the engine's mapping.
  const relayStates = [0, 0, 0, 0];
  if (confirmedCount >= 1 && confirmedCount <= 4) relayStates[confirmedCount - 1] = 1;
  else if (confirmedCount === 5) relayStates.fill(1);

  // Show the confirmed count, the value that drives the relays; the raw
  // per-frame count is shown underneath while a new count is being confirmed.
  const displayCount = confirmedCount;
  const pendingCount = liveCount >= 0 && liveCount !== confirmedCount ? liveCount : -1;

  return (
    <div className="min-h-screen text-white" style={{ background: "#08080c", fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", system-ui, sans-serif' }}>
      {/* Nav */}
      <nav className="fixed top-0 inset-x-0 z-50 border-b border-white/[0.06]" style={{ background: "rgba(8,8,12,0.85)", backdropFilter: "blur(20px)", WebkitBackdropFilter: "blur(20px)" }}>
        <div className="max-w-[1000px] mx-auto px-6 h-14 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg flex items-center justify-center text-sm font-bold text-white" style={{ background: "#DC2626" }}>G</div>
            <span className="text-[15px] font-semibold tracking-tight">GestureControl</span>
          </div>
          <div className="flex items-center gap-8">
            {["Overview", "Demo", "Architecture", "Stack"].map((s) => (
              <a key={s} href={`#${s.toLowerCase()}`} className="text-[13px] text-gray-500 hover:text-white transition-colors no-underline">{s}</a>
            ))}
            <a href="https://github.com/carlous-roy/GestureControl-Engine" target="_blank" rel="noopener noreferrer"
              className="flex items-center gap-1.5 text-[13px] text-gray-500 hover:text-white transition-colors no-underline">
              <svg width="15" height="15" viewBox="0 0 16 16" fill="currentColor"><path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z"/></svg>
              Source
            </a>
          </div>
        </div>
      </nav>

      <main className="max-w-[1000px] mx-auto px-6 pt-24 pb-16">
        {/* ── Hero ── */}
        <section id="overview" className="mb-16" style={{ animation: "fadeIn 0.8s ease-out" }}>
          <p className="font-mono text-sm font-medium tracking-widest uppercase mb-4" style={{ color: "#DC2626" }}>B.E. Electronics & Communication</p>
          <h1 className="font-extrabold tracking-tight mb-5" style={{ fontSize: "clamp(32px, 5vw, 52px)", lineHeight: 1.08, letterSpacing: "-0.03em" }}>
            AI Gesture Based<br />
            <span style={{ color: "#DC2626" }}>Home Automation</span>
          </h1>
          <p className="text-gray-400 max-w-[520px] mb-8" style={{ fontSize: "clamp(15px, 1.6vw, 18px)", lineHeight: 1.7 }}>
            Finger counting from a webcam that drives a 4-channel relay module through an Arduino UNO. This page runs the same classifier in your browser with the relays simulated. Show 0-5 fingers to switch appliances on and off.
          </p>
          <div className="flex gap-3">
            <a href="#demo" className="px-6 py-2.5 rounded-full font-medium text-sm text-white no-underline transition-all hover:-translate-y-0.5"
              style={{ background: "#DC2626", boxShadow: "0 4px 24px rgba(220,38,38,0.2)" }}>Try Live Demo</a>
            <a href="https://github.com/carlous-roy/GestureControl-Engine" target="_blank" rel="noopener noreferrer"
              className="px-6 py-2.5 rounded-full font-medium text-sm text-white no-underline border border-white/[0.06] bg-white/[0.02] hover:border-red-500/20 transition-all">View Source</a>
          </div>

          {/* Stats */}
          <div className="grid grid-cols-4 gap-3 mt-14">
            {[
              { value: "21", label: "Hand Landmarks" },
              { value: String(CONFIRM_FRAMES), label: "Frames to confirm" },
              { value: "6", label: "Gesture States" },
              { value: "4", label: "Relay Channels" },
            ].map((s) => (
              <div key={s.label} className="bg-white/[0.02] border border-white/[0.06] rounded-3xl p-5 text-center"
                style={{ transition: "border-color 0.3s, transform 0.25s" }}
                onMouseEnter={e => { e.currentTarget.style.borderColor = "rgba(220,38,38,0.15)"; e.currentTarget.style.transform = "translateY(-2px)"; }}
                onMouseLeave={e => { e.currentTarget.style.borderColor = ""; e.currentTarget.style.transform = ""; }}>
                <div className="text-2xl font-bold">{s.value}</div>
                <div className="text-[10px] text-gray-500 uppercase tracking-widest mt-1 font-mono">{s.label}</div>
              </div>
            ))}
          </div>
        </section>

        {/* ── Live Demo ── */}
        <section id="demo" className="mb-16" style={{ animation: "slideUp 0.5s ease-out 0.2s both" }}>
          <p className="font-mono text-sm font-medium tracking-widest uppercase mb-2" style={{ color: "#DC2626" }}>Live Demo</p>
          <p className="text-gray-400 text-sm mb-6 max-w-[520px]">
            Runs MediaPipe Hands entirely in your browser. No data leaves your device. Show 0-5 fingers; a count that holds for {CONFIRM_FRAMES} consecutive frames switches the relay panel, exactly as it switches the relays in the Python engine.
          </p>

          <div className="grid grid-cols-[1fr_280px] gap-5 items-start">
            {/* Camera */}
            <div className="bg-white/[0.02] border border-white/[0.06] rounded-3xl overflow-hidden relative">
              {!demoActive ? (
                <div className="aspect-[4/3] flex flex-col items-center justify-center gap-4">
                  <div className="w-14 h-14 rounded-2xl flex items-center justify-center" style={{ background: "rgba(220,38,38,0.08)" }}>
                    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#DC2626" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/><circle cx="12" cy="13" r="4"/>
                    </svg>
                  </div>
                  <p className="text-sm text-gray-500">Camera access required</p>
                  <button onClick={() => setDemoActive(true)}
                    className="px-6 py-2.5 rounded-full font-medium text-sm text-white border-none cursor-pointer transition-all hover:-translate-y-0.5"
                    style={{ background: "#DC2626", boxShadow: "0 4px 24px rgba(220,38,38,0.2)", fontFamily: "inherit" }}>
                    Start Demo
                  </button>
                </div>
              ) : (
                <div className="relative aspect-[4/3]">
                  <video ref={videoRef} className="absolute w-0 h-0 opacity-0" playsInline />
                  <canvas ref={canvasRef} className="w-full h-full object-cover" style={{ transform: "scaleX(-1)" }} />

                  {isLoading && (
                    <div className="absolute inset-0 flex flex-col items-center justify-center gap-3" style={{ background: "rgba(8,8,12,0.92)" }}>
                      <div className="w-7 h-7 border-[3px] border-white/[0.06] rounded-full" style={{ borderTopColor: "#DC2626", animation: "spin 0.8s linear infinite" }} />
                      <p className="text-xs text-gray-500">Loading MediaPipe model...</p>
                    </div>
                  )}

                  {error && (
                    <div className="absolute inset-0 flex items-center justify-center p-6" style={{ background: "rgba(8,8,12,0.92)" }}>
                      <p className="text-sm text-center max-w-xs" style={{ color: "#DC2626" }}>{error}</p>
                    </div>
                  )}

                  {!isLoading && !error && (
                    <div className="absolute top-3 right-3 px-2.5 py-1 rounded-lg text-xs font-mono font-semibold"
                      style={{ background: "rgba(0,0,0,0.6)", backdropFilter: "blur(8px)", color: fps > 20 ? "#4ade80" : "#facc15" }}>
                      {fps} FPS
                    </div>
                  )}

                  <button onClick={() => setDemoActive(false)}
                    className="absolute bottom-3 right-3 px-3.5 py-1.5 rounded-lg text-xs font-semibold text-white border-none cursor-pointer"
                    style={{ background: "rgba(220,38,38,0.9)", fontFamily: "inherit" }}>
                    Stop
                  </button>
                </div>
              )}
            </div>

            {/* Control panel */}
            <div className="flex flex-col gap-4">
              {/* Finger count */}
              <div className="bg-white/[0.02] border border-white/[0.06] rounded-3xl p-5 text-center"
                style={{ transition: "border-color 0.3s, transform 0.25s" }}
                onMouseEnter={e => { e.currentTarget.style.borderColor = "rgba(220,38,38,0.15)"; e.currentTarget.style.transform = "translateY(-2px)"; }}
                onMouseLeave={e => { e.currentTarget.style.borderColor = ""; e.currentTarget.style.transform = ""; }}>
                <div className="text-[10px] text-gray-500 uppercase tracking-widest font-mono mb-2">Detected Fingers</div>
                <div className="text-5xl font-extrabold font-mono leading-none" style={{ color: displayCount >= 0 ? "#fff" : "rgba(255,255,255,0.15)" }}>
                  {displayCount >= 0 ? displayCount : "--"}
                </div>
                <div className="text-xs font-medium mt-2" style={{ color: confirmedCount >= 0 ? "#DC2626" : "rgba(255,255,255,0.2)" }}>
                  {confirmedCount >= 0 ? (GESTURE_MAP[confirmedCount]?.action || "Unknown") : "No hand detected"}
                </div>
                {pendingCount >= 0 && (
                  <div className="text-[10px] text-gray-400 font-mono mt-3">
                    Seeing {pendingCount}: frame {Math.min(runLength, CONFIRM_FRAMES)} of {CONFIRM_FRAMES}
                  </div>
                )}
                {liveCount < 0 && confirmedCount >= 0 && (
                  <div className="text-[10px] text-gray-600 mt-1 font-mono">No hand: relays hold their state</div>
                )}
              </div>

              {/* Relay panel */}
              <div className="bg-white/[0.02] border border-white/[0.06] rounded-3xl p-5"
                style={{ transition: "border-color 0.3s, transform 0.25s" }}
                onMouseEnter={e => { e.currentTarget.style.borderColor = "rgba(220,38,38,0.15)"; e.currentTarget.style.transform = "translateY(-2px)"; }}
                onMouseLeave={e => { e.currentTarget.style.borderColor = ""; e.currentTarget.style.transform = ""; }}>
                <div className="text-[10px] text-gray-500 uppercase tracking-widest font-mono mb-3">Relay Panel</div>
                <div className="flex flex-col gap-2">
                  {[1, 2, 3, 4].map((relay, i) => (
                    <div key={relay} className="flex items-center justify-between px-3 py-2.5 rounded-xl transition-all"
                      style={{
                        background: relayStates[i] ? "rgba(220,38,38,0.08)" : "rgba(255,255,255,0.02)",
                        border: `1px solid ${relayStates[i] ? "rgba(220,38,38,0.2)" : "rgba(255,255,255,0.06)"}`,
                      }}>
                      <div className="flex items-center gap-2.5">
                        <div className="w-2 h-2 rounded-full transition-all"
                          style={{
                            background: relayStates[i] ? "#4ade80" : "rgba(255,255,255,0.1)",
                            boxShadow: relayStates[i] ? "0 0 8px rgba(74,222,128,0.5)" : "none",
                          }} />
                        <span className="text-xs font-medium">Appliance {relay}</span>
                      </div>
                      <span className="text-[10px] font-semibold font-mono uppercase tracking-wide"
                        style={{ color: relayStates[i] ? "#4ade80" : "rgba(255,255,255,0.2)" }}>
                        {relayStates[i] ? "ON" : "OFF"}
                      </span>
                    </div>
                  ))}
                </div>
              </div>

              {/* Status */}
              <div className="bg-white/[0.02] border border-white/[0.06] rounded-3xl px-5 py-3 flex items-center gap-2.5">
                <div className="w-2 h-2 rounded-full" style={{ background: demoActive && !isLoading ? "#f59e0b" : "rgba(255,255,255,0.15)" }} />
                <span className="text-xs text-gray-500">Arduino: Simulation Mode</span>
              </div>
            </div>
          </div>
        </section>

        {/* ── Architecture ── */}
        <section id="architecture" className="mb-16">
          <p className="font-mono text-sm font-medium tracking-widest uppercase mb-2" style={{ color: "#DC2626" }}>System Architecture</p>
          <p className="text-gray-400 text-sm mb-6 max-w-[520px]">
            A three-stage pipeline from camera input to appliance control. Frame rate and per-stage latency are measured with the engine's <code>gesturecontrol bench</code> command; the repository README holds the table.
          </p>

          {/* Pipeline */}
          <div className="bg-white/[0.02] border border-white/[0.06] rounded-3xl p-8 mb-5"
            style={{ transition: "border-color 0.3s, box-shadow 0.3s" }}
            onMouseEnter={e => { e.currentTarget.style.borderColor = "rgba(220,38,38,0.15)"; e.currentTarget.style.boxShadow = "0 0 50px rgba(220,38,38,0.04)"; }}
            onMouseLeave={e => { e.currentTarget.style.borderColor = ""; e.currentTarget.style.boxShadow = ""; }}>

            <div className="grid grid-cols-5 gap-0 items-center mb-6">
              {[
                { title: "Camera Input", desc: "Webcam frames via OpenCV in the engine, getUserMedia in this page", time: "capture", color: "#3b82f6" },
                null,
                { title: "MediaPipe Hands", desc: "Palm detector when no hand is tracked, 21-landmark model on every frame", time: "inference", color: "#0F9D58" },
                null,
                { title: "Finger Counting", desc: "One Euro filter, finger rules in the hand's own frame with hysteresis, confirmation over consecutive frames", time: "classify", color: "#f59e0b" },
              ].map((item, idx) =>
                item === null ? (
                  <div key={idx} className="flex justify-center">
                    <svg width="28" height="10" viewBox="0 0 28 10" fill="none"><path d="M0 5H24M24 5L19 1M24 5L19 9" stroke="rgba(255,255,255,0.15)" strokeWidth="1.5"/></svg>
                  </div>
                ) : (
                  <div key={item.title} className="bg-white/[0.02] border border-white/[0.06] rounded-2xl p-4">
                    <div className="w-2 h-2 rounded-full mb-3" style={{ background: item.color }} />
                    <div className="text-[13px] font-semibold mb-1">{item.title}</div>
                    <div className="text-[11px] text-gray-500 leading-relaxed mb-3">{item.desc}</div>
                    <div className="text-[10px] font-semibold font-mono" style={{ color: item.color }}>{item.time}</div>
                  </div>
                )
              )}
            </div>

            <div className="flex justify-center mb-6">
              <svg width="10" height="28" viewBox="0 0 10 28" fill="none"><path d="M5 0V24M5 24L1 19M5 24L9 19" stroke="rgba(255,255,255,0.15)" strokeWidth="1.5"/></svg>
            </div>

            <div className="grid grid-cols-3 gap-3">
              {[
                { title: "Firmata over serial", desc: "The host writes pin levels over USB with pyFirmata2 and sends a heartbeat for the optional watchdog sketch", color: "#00979D" },
                { title: "Arduino UNO (ATmega328P)", desc: "Drives the module inputs from pins 7 to 4; with the watchdog sketch it releases every relay if the heartbeat stops", color: "#00979D" },
                { title: "4-Channel Relay Module", desc: "Optocoupler-isolated relays switch mains voltage to control appliances", color: "#DC2626" },
              ].map((item) => (
                <div key={item.title} className="bg-white/[0.02] border border-white/[0.06] rounded-2xl p-4">
                  <div className="w-2 h-2 rounded-full mb-3" style={{ background: item.color }} />
                  <div className="text-[13px] font-semibold mb-1">{item.title}</div>
                  <div className="text-[11px] text-gray-500 leading-relaxed">{item.desc}</div>
                </div>
              ))}
            </div>
          </div>

          {/* Gesture mapping table */}
          <div className="bg-white/[0.02] border border-white/[0.06] rounded-3xl overflow-hidden mb-5">
            <div className="px-5 py-3 border-b border-white/[0.06]">
              <span className="font-mono text-sm font-medium tracking-widest uppercase" style={{ color: "#DC2626" }}>Gesture Mapping</span>
            </div>
            {GESTURE_MAP.map((g, i) => (
              <div key={g.fingers} className="grid grid-cols-[50px_1fr_1fr_120px] items-center px-5 py-3"
                style={{ borderBottom: i < GESTURE_MAP.length - 1 ? "1px solid rgba(255,255,255,0.03)" : "none" }}>
                <div className="w-8 h-8 rounded-lg bg-white/[0.04] flex items-center justify-center text-sm font-bold font-mono">{g.fingers}</div>
                <span className="text-[13px]">{g.fingers} {g.fingers === 1 ? "finger" : "fingers"}</span>
                <span className="text-[13px] text-gray-500">{g.label}</span>
                <span className="text-[11px] font-semibold font-mono" style={{ color: g.fingers === 0 ? "rgba(255,255,255,0.3)" : "#DC2626" }}>{g.action}</span>
              </div>
            ))}
          </div>

          {/* Algorithm */}
          <div className="bg-white/[0.02] border border-white/[0.06] rounded-3xl p-6">
            <span className="font-mono text-sm font-medium tracking-widest uppercase" style={{ color: "#DC2626" }}>Algorithm</span>
            <div className="grid grid-cols-2 gap-6 mt-4">
              <div>
                <div className="text-xs font-semibold text-gray-300 mb-2">Hand frame and thumb</div>
                <p className="text-[12px] text-gray-500 leading-relaxed">
                  Every measurement is taken in a frame attached to the hand: the up axis runs from the wrist (landmark 0) to the middle-finger MCP (landmark 9), the side axis points to the thumb side, and palm width (index MCP 5 to pinky MCP 17) is the unit of length. The thumb counts as extended when its tip (landmark 4) lies beyond the index MCP along the side axis by more than {DEFAULT_RULES.thumb.raise_threshold} palm widths, and stays extended until that drops below {DEFAULT_RULES.thumb.lower_threshold}. Because the frame turns with the hand, the rule holds for either hand, mirrored video, camera distance and in-plane rotation.
                </p>
              </div>
              <div>
                <div className="text-xs font-semibold text-gray-300 mb-2">Fingers, filtering and confirmation</div>
                <p className="text-[12px] text-gray-500 leading-relaxed">
                  Landmarks are smoothed by a One Euro filter (Casiez, Roussel and Vogel, 2012) before the rules run. A finger counts as extended when its tip lies beyond its PIP joint along the up axis by more than {DEFAULT_RULES.finger.raise_threshold} palm widths and stays extended until that drops below {DEFAULT_RULES.finger.lower_threshold}. A count reaches the relays only after {CONFIRM_FRAMES} consecutive frames; losing the hand resets that run but keeps the relays as they are. Show a fist to turn everything off. The constants come from the same rules.json the Python engine reads.
                </p>
              </div>
            </div>
          </div>
        </section>

        {/* ── Tech Stack ── */}
        <section id="stack" className="mb-16">
          <p className="font-mono text-sm font-medium tracking-widest uppercase mb-6" style={{ color: "#DC2626" }}>Tech Stack</p>
          <div className="grid grid-cols-3 gap-3 mb-5">
            {TECH_STACK.map((t) => (
              <div key={t.name} className="bg-white/[0.02] border border-white/[0.06] rounded-3xl p-5"
                style={{ transition: "border-color 0.3s, transform 0.25s" }}
                onMouseEnter={e => { e.currentTarget.style.borderColor = "rgba(220,38,38,0.15)"; e.currentTarget.style.transform = "translateY(-2px)"; }}
                onMouseLeave={e => { e.currentTarget.style.borderColor = ""; e.currentTarget.style.transform = ""; }}>
                <div className="w-2.5 h-2.5 rounded-full mb-4" style={{ background: t.color }} />
                <div className="text-[14px] font-semibold mb-1">{t.name}</div>
                <div className="text-[11px] text-gray-500">{t.role}</div>
              </div>
            ))}
          </div>

          {/* Wiring */}
          <div className="bg-white/[0.02] border border-white/[0.06] rounded-3xl p-6 mb-5">
            <span className="font-mono text-sm font-medium tracking-widest uppercase" style={{ color: "#DC2626" }}>Hardware Wiring</span>
            <pre className="mt-4 bg-black/30 rounded-xl p-5 text-[12px] text-gray-400 leading-relaxed overflow-x-auto" style={{ fontFamily: "'SF Mono', Menlo, Consolas, monospace" }}>{
`Arduino UNO          4-Channel Relay Module
─────────────        ─────────────────────
Pin 7  ──────────>   IN1  (Relay 1 → Appliance 1)
Pin 6  ──────────>   IN2  (Relay 2 → Appliance 2)
Pin 5  ──────────>   IN3  (Relay 3 → Appliance 3)
Pin 4  ──────────>   IN4  (Relay 4 → Appliance 4)
5V     ──────────>   VCC
GND    ──────────>   GND`}</pre>
          </div>

          {/* Project details */}
          <div className="bg-white/[0.02] border border-white/[0.06] rounded-3xl p-6 grid grid-cols-2 gap-8">
            <div>
              <div className="text-[10px] text-gray-500 uppercase tracking-widest font-mono mb-3">Project Details</div>
              {[
                ["Degree", "B.E. Electronics & Communication"],
                ["Institution", "Sathyabama Institute of Science and Technology"],
                ["Year", "2022"],
                ["Authors", "Roy Carlous Christudass, Vasanth Mathew B"],
                ["Guide", "Dr. T. Ravi, M.E., Ph.D."],
              ].map(([k, v]) => (
                <div key={k} className="flex gap-3 mb-1.5">
                  <span className="text-[12px] text-gray-600 min-w-[75px]">{k}</span>
                  <span className="text-[12px] text-gray-300">{v}</span>
                </div>
              ))}
            </div>
            <div>
              <div className="text-[10px] text-gray-500 uppercase tracking-widest font-mono mb-3">Key Features</div>
              {[
                "Same filter, rules and confirmation as the Python engine, checked against shared golden vectors",
                "Finger and thumb rules measured in the hand's own frame",
                `${CONFIRM_FRAMES}-frame confirmation before a relay changes`,
                "Relays hold their state when the hand leaves the frame",
                "Hardware-free simulator, unit tests and CI in the engine",
                "Fail-safe relay handling with an optional watchdog firmware",
              ].map((f) => (
                <div key={f} className="flex items-start gap-2 mb-1.5">
                  <span className="mt-[6px] w-1 h-1 rounded-full flex-shrink-0" style={{ background: "#DC2626" }} />
                  <span className="text-[12px] text-gray-400 leading-relaxed">{f}</span>
                </div>
              ))}
            </div>
          </div>
        </section>
      </main>

      {/* Footer */}
      <footer className="border-t border-white/[0.06] py-6">
        <div className="max-w-[1000px] mx-auto px-6 flex items-center justify-between text-xs text-gray-600">
          <span>GestureControl · AI Gesture Home Automation · <a href="https://roycarlous.com" className="hover:text-white transition-colors no-underline text-gray-500">Roy Carlous Christudass</a></span>
          <span>Browser demo · <a href="https://github.com/carlous-roy/GestureControl-Engine" className="hover:text-white transition-colors no-underline text-gray-500">Full version on GitHub</a></span>
        </div>
      </footer>

      <style>{`
        @keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
        @keyframes slideUp { from { opacity: 0; transform: translateY(16px); } to { opacity: 1; transform: translateY(0); } }
        @keyframes spin { to { transform: rotate(360deg); } }
        ::selection { background: rgba(220, 38, 38, 0.2); color: inherit; }
        ::-webkit-scrollbar { width: 5px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: rgba(220, 38, 38, 0.25); border-radius: 4px; }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        html { scroll-behavior: smooth; }
        body { background: #08080c; }
        @media (max-width: 768px) {
          .grid-cols-\\[1fr_280px\\] { grid-template-columns: 1fr !important; }
          .grid-cols-5 { grid-template-columns: 1fr !important; }
          .grid-cols-5 svg[viewBox="0 0 28 10"] { transform: rotate(90deg); }
          .grid-cols-3 { grid-template-columns: 1fr 1fr !important; }
          .grid-cols-4 { grid-template-columns: 1fr 1fr !important; }
          .grid-cols-2 { grid-template-columns: 1fr !important; }
        }
      `}</style>
    </div>
  );
}
