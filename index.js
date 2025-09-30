import http from "http";
import { WebSocketServer, WebSocket } from "ws";

const OPENAI_API_KEY = process.env.OPENAI_API_KEY;
const MODEL = process.env.OPENAI_REALTIME_MODEL || "gpt-4o-realtime-preview";
const PORT = Number(process.env.PORT || 5050);

if (!OPENAI_API_KEY) {
  console.error("❌ Set OPENAI_API_KEY");
  process.exit(1);
}

// --- HTTP: health + simple 404 ---
const server = http.createServer((req, res) => {
  if (req.method === "GET" && (req.url === "/" || req.url === "/health")) {
    res.writeHead(200, { "content-type": "application/json" });
    return res.end(JSON.stringify({ ok: true, service: "wsc-tip-relay" }));
  }
  res.writeHead(404, { "content-type": "text/plain" });
  res.end("Not Found");
});

// --- WS server for Twilio <Connect><Stream> ---
const wss = new WebSocketServer({ noServer: true, perMessageDeflate: false });

server.on("upgrade", (req, socket, head) => {
  if (!req.url || !req.url.startsWith("/media-stream")) {
    socket.destroy();
    return;
  }
  wss.handleUpgrade(req, socket, head, (ws) => {
    wss.emit("connection", ws, req);
  });
});

// --- Bridge Twilio <-> OpenAI Realtime with buffering + size-based commits ---
wss.on("connection", (twilioWS) => {
  console.log("✅ Twilio connected to /media-stream");

  const oaWS = new WebSocket(
    `wss://api.openai.com/v1/realtime?model=${encodeURIComponent(MODEL)}`,
    {
      headers: {
        Authorization: `Bearer ${OPENAI_API_KEY}`,
        "OpenAI-Beta": "realtime=v1",
      },
    }
  );

  let streamSid = null;
  let oaReady = false;
  const pending = []; // queued base64 PCMU frames until session is configured

  // commit only after ~100ms of audio (≈800 bytes @ 8kHz G.711 μ-law)
  let bytesSinceCommit = 0;
  const COMMIT_THRESHOLD = 800;

  const tryCommit = () => {
    if (bytesSinceCommit >= COMMIT_THRESHOLD && oaWS.readyState === WebSocket.OPEN) {
      oaWS.send(JSON.stringify({ type: "input_audio_buffer.commit" }));
      bytesSinceCommit = 0;
    }
  };

  const sendToOA = (b64) => {
    if (!oaReady || oaWS.readyState !== WebSocket.OPEN) {
      pending.push(b64);
      return;
    }
    // append audio
    oaWS.send(JSON.stringify({ type: "input_audio_buffer.append", audio: b64 }));
    // count raw bytes and commit when we’ve got enough
    try {
      bytesSinceCommit += Buffer.from(b64, "base64").length;
    } catch {}
    tryCommit();
  };

  oaWS.on("open", () => {
    console.log("✅ OpenAI Realtime connected");
    // Configure session BEFORE any response
    oaWS.send(
      JSON.stringify({
        type: "session.update",
        session: {
          instructions:
            "You are the Westside Current tipline reporter. Collect who/what/when/where/how, ask 2–3 follow-ups, avoid legal advice, then read back a one-paragraph summary for confirmation.",
          modalities: ["audio", "text"],          // must include text
          turn_detection: { type: "server_vad" },
          input_audio_format: "g711_ulaw",        // Twilio PCMU
          output_audio_format: "g711_ulaw",       // Twilio PCMU
          voice: "alloy",
        },
      })
    );
  });

  // Log non-audio events to surface errors/state
  oaWS.on("message", (buf) => {
    let msg;
    try {
      msg = JSON.parse(buf.toString());
    } catch {
      return;
    }

    if (msg.type && msg.type !== "response.output_audio.delta") {
      console.log("OA evt:", msg.type);
      if (msg.error) console.log("OA error:", msg.error);
    }

    if (msg.type === "session.updated") {
      oaReady = true;

      // Flush any queued frames now that session is configured
      while (pending.length && oaWS.readyState === WebSocket.OPEN) {
        const frame = pending.shift();
        oaWS.send(JSON.stringify({ type: "input_audio_buffer.append", audio: frame }));
        try {
          bytesSinceCommit += Buffer.from(frame, "base64").length;
        } catch {}
      }
      tryCommit();

      // Kick off an initial greeting AFTER session is fully set
      oaWS.send(JSON.stringify({ type: "response.create" }));
      return;
    }

    // Model speaking → send frames back to Twilio
    if (msg.type === "response.output_audio.delta" && msg.delta) {
      if (streamSid) {
        twilioWS.send(
          JSON.stringify({
            event: "media",
            streamSid,
            media: { payload: msg.delta }, // base64 PCMU
          })
        );
      }
      return;
    }
  });

  // Caller → Model
  twilioWS.on("message", (buf) => {
    try {
      const data = JSON.parse(buf.toString());
      if (data.event === "start") {
        streamSid = data.start.streamSid;
        console.log("Twilio stream started:", streamSid);
        bytesSinceCommit = 0; // reset for new stream
      } else if (data.event === "media" && data.media?.payload) {
        sendToOA(data.media.payload);
      } else if (data.event === "stop") {
        // optional: flush if we have >=100ms pending
        if (bytesSinceCommit >= COMMIT_THRESHOLD && oaWS.readyState === WebSocket.OPEN) {
          oaWS.send(JSON.stringify({ type: "input_audio_buffer.commit" }));
          bytesSinceCommit = 0;
        }
        if (oaWS.readyState === WebSocket.OPEN) oaWS.close(1000, "call ended");
      }
    } catch (e) {
      console.error("Twilio message parse error:", e);
    }
  });

  // Cleanup
  twilioWS.on("close", () => {
    if (oaWS.readyState === WebSocket.OPEN) oaWS.close(1000, "twilio socket closed");
    console.log("❌ Twilio disconnected");
  });
  oaWS.on("close", () => {
    console.log("❌ OpenAI Realtime closed");
  });
  oaWS.on("error", (e) => console.error("OpenAI WS error:", e));
});

server.listen(PORT, "0.0.0.0", () => {
  console.log(`🚀 Relay listening on ${PORT}`);
});

