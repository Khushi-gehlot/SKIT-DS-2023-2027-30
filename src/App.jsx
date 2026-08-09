// src/App.jsx
import { useEffect, useState } from "react";
import axios from "axios";
import { FaMicrophone, FaRobot, FaBolt, FaVolumeUp } from "react-icons/fa";

const API_BASE = "http://localhost:8000";

function App() {
  const [availableCommands, setAvailableCommands] = useState([]);
  const [status, setStatus] = useState("");
  const [listening, setListening] = useState(false);
  const [lastHeard, setLastHeard] = useState("");
  const [history, setHistory] = useState([]);
  const [alwaysOn, setAlwaysOn] = useState(false);

  // Load commands list (for info / help panel)
  useEffect(() => {
    axios
      .get(`${API_BASE}/api/commands`)
      .then((res) => setAvailableCommands(res.data || []))
      .catch((err) => {
        console.error("Error loading commands:", err);
        setAvailableCommands([]);
      });
  }, []);

  // Auto-start always-on wake word mode on app load,
  // and stop it when the tab is closed/refreshed.
  useEffect(() => {
    const startAlwaysOn = async () => {
      try {
        setStatus("Starting always-on wake word listening...");
        const res = await axios.post(`${API_BASE}/api/always_on/start`);
        setAlwaysOn(true);
        setStatus(res.data?.message || "Always-on listening started.");
      } catch (error) {
        console.error("Error auto-starting always-on:", error);
        setStatus("Could not start always-on mode automatically.");
      }
    };

    startAlwaysOn();

    return () => {
      axios
        .post(`${API_BASE}/api/always_on/stop`)
        .catch((err) =>
          console.error("Error auto-stopping always-on:", err)
        );
    };
  }, []);

  const startListening = async () => {
    if (listening) return;

    setListening(true);
    setStatus("Listening... Speak your wake word, then your command.");

    try {
      const res = await axios.post(`${API_BASE}/api/listen`);
      const data = res.data;

      setListening(false);
      setLastHeard(data.recognized || "");
      setStatus(data.message);

      setHistory((prev) => [
        {
          heard: data.recognized || "(no speech)",
          message: data.message,
          success: data.success,
          time: new Date().toLocaleTimeString(),
        },
        ...prev,
      ]);
    } catch (error) {
      console.error(error);
      setListening(false);
      setStatus("Error: could not reach backend.");
      setHistory((prev) => [
        {
          heard: "(backend error)",
          message: "Error: could not reach backend.",
          success: false,
          time: new Date().toLocaleTimeString(),
        },
        ...prev,
      ]);
    }
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex items-center justify-center p-4">
      <div className="w-full max-w-5xl mx-auto space-y-6">
        {/* Header */}
        <header className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
          <div>
            <h1 className="text-3xl md:text-4xl font-bold flex items-center gap-3">
              <FaRobot className="text-emerald-400" />
              VyasOS Voice Assistant
            </h1>
            <p className="text-slate-400 mt-1 text-sm md:text-base">
              Say commands like{" "}
              <span className="text-emerald-300">
                &quot;open youtube&quot;, &quot;open settings&quot;,
                &quot;scroll down&quot;, &quot;notepad&quot;, &quot;shutdown&quot;
              </span>{" "}
              and your PC will obey. First say your wake word like{" "}
              <span className="text-emerald-300">&quot;hello vyas&quot;</span>.
            </p>
          </div>
          <span className="px-3 py-1 rounded-full bg-emerald-500/10 text-emerald-300 text-xs md:text-sm border border-emerald-500/40">
            Backend: {API_BASE}
          </span>
        </header>

        {/* Main layout */}
        <div className="grid md:grid-cols-[3fr,2fr] gap-6">
          {/* Left: Voice panel */}
          <section className="bg-slate-900/70 border border-slate-800 rounded-3xl p-6 shadow-2xl shadow-slate-900/60 flex flex-col items-center">
            <div className="flex flex-col items-center gap-2 mb-6">
              <div className="w-20 h-20 rounded-full bg-gradient-to-tr from-emerald-500 to-cyan-400 flex items-center justify-center shadow-lg shadow-emerald-500/40">
                <FaRobot className="text-slate-950" size={36} />
              </div>
              <h2 className="text-xl font-semibold mt-2">Hey, I&apos;m Vyas</h2>
              <p className="text-sm text-slate-400 text-center max-w-md">
                Always-on mode starts automatically. You can just say your wake
                word like{" "}
                <span className="text-emerald-300">&quot;hello vyas&quot;</span>{" "}
                then say a command, or tap the mic to trigger one-shot listening.
              </p>
            </div>

            {/* Mic button */}
            <button
              onClick={startListening}
              className={`relative w-28 h-28 rounded-full flex items-center justify-center 
                transition-all duration-300 border 
                ${
                  listening
                    ? "bg-emerald-500 border-emerald-300 shadow-[0_0_40px_rgba(16,185,129,0.8)] scale-105"
                    : "bg-slate-800 border-slate-600 hover:bg-slate-700 hover:border-emerald-400"
                }`}
            >
              {listening && (
                <span className="absolute inline-flex h-full w-full rounded-full bg-emerald-500/30 animate-ping" />
              )}
              <FaMicrophone
                size={40}
                className={listening ? "text-slate-950" : "text-emerald-300"}
              />
            </button>
            <p className="mt-3 text-sm text-slate-400">
              {listening
                ? "Listening... speak wake word, then command."
                : alwaysOn
                ? "Always-on is active. You can speak anytime, or tap mic for one-shot."
                : "Tap the mic to start listening."}
            </p>

            {/* Status / last command */}
            <div className="mt-6 w-full space-y-4">
              <div>
                <p className="text-xs uppercase tracking-wide text-slate-500 mb-1">
                  Last heard
                </p>
                <div className="min-h-[2.5rem] rounded-xl bg-slate-950/60 border border-slate-800 px-3 py-2 text-sm text-slate-200">
                  {lastHeard || "—"}
                </div>
              </div>

              <div>
                <p className="text-xs uppercase tracking-wide text-slate-500 mb-1">
                  Status
                </p>
                <div className="min-h-[3rem] rounded-xl bg-slate-950/60 border border-slate-800 px-3 py-2 text-sm text-slate-200">
                  {status || "Idle. Say your wake word or tap the mic."}
                </div>
              </div>
            </div>
          </section>

          {/* Right: Tips + history */}
          <section className="space-y-4">
            {/* Tips / example commands */}
            <div className="bg-slate-900/70 border border-slate-800 rounded-3xl p-5">
              <h2 className="text-lg font-semibold mb-2 flex items-center gap-2">
                <FaBolt className="text-emerald-400" />
                Example Commands
              </h2>
              <p className="text-xs text-slate-400 mb-3">
                First say your wake word (e.g. &quot;hello vyas&quot;), then:
              </p>
              <ul className="text-sm text-slate-200 space-y-1">
                <li>• &quot;open youtube&quot;</li>
                <li>• &quot;open settings&quot;</li>
                <li>• &quot;scroll down&quot;</li>
                <li>• &quot;scroll up&quot;</li>
                <li>• &quot;take screenshot&quot;</li>
                <li>• &quot;open notepad&quot;</li>
                <li>• &quot;volume up&quot; / &quot;volume down&quot;</li>
                <li>• &quot;shutdown&quot; / &quot;restart&quot;</li>
              </ul>
            </div>

            {/* Available commands list (from backend) */}
            <div className="bg-slate-900/70 border border-slate-800 rounded-3xl p-5">
              <h2 className="text-lg font-semibold mb-2 flex items-center gap-2">
                <FaVolumeUp className="text-emerald-400" />
                All Supported Keywords
              </h2>
              {availableCommands.length === 0 ? (
                <p className="text-sm text-slate-400">
                  Could not load commands from backend.
                </p>
              ) : (
                <div className="flex flex-wrap gap-2 max-h-40 overflow-y-auto pr-1 text-xs">
                  {availableCommands.map((cmd) => (
                    <span
                      key={cmd}
                      className="px-3 py-1.5 rounded-full bg-slate-800 text-slate-100 border border-slate-700"
                    >
                      {cmd}
                    </span>
                  ))}
                </div>
              )}
            </div>

            {/* History */}
            <div className="bg-slate-900/70 border border-slate-800 rounded-3xl p-5">
              <h2 className="text-lg font-semibold mb-3">Conversation Log</h2>
              {history.length === 0 ? (
                <p className="text-sm text-slate-400">
                  No commands yet. Say your wake word or click the microphone!
                </p>
              ) : (
                <ul className="space-y-2 max-h-48 overflow-y-auto pr-1 text-sm">
                  {history.map((item, idx) => (
                    <li
                      key={idx}
                      className="border border-slate-800 rounded-xl px-3 py-2 flex flex-col gap-1"
                    >
                      <div className="flex justify-between items-center">
                        <span className="font-mono text-emerald-300">
                          {item.heard}
                        </span>
                        <span className="text-xs text-slate-500">
                          {item.time}
                        </span>
                      </div>
                      <p
                        className={`text-xs ${
                          item.success
                            ? "text-emerald-300"
                            : "text-rose-300"
                        }`}
                      >
                        {item.message}
                      </p>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}

export default App;
