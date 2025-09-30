import http from "http";
import { WebSocketServer, WebSocket } from "ws";

const OPENAI_API_KEY = process.env.OPENAI_API_KEY;
const MODEL = process.env.OPENAI_REALTIME_MODEL || "gpt-4o-realtime-preview";
const PORT = Number(process.env.PORT || 5050);

if (!OPENAI_API_KEY) {
  console.error("❌ Set OPENAI_API_KEY");
  process.exit(1);
}

// --- HTTP: health check + simple 404 ---
const server = http.createServer((req, res) => {
  if (req.method === "GET" && (req.url === "/" || req.url === "/health")) {
    res.writeHead(200, { "content-type": "application/json" });
    return res.end(JSON.stringify({ ok: true, service: "wsc-tip-relay" }));
  }
  res.writeHead(404, { "content-type": "text/plain" });
  res.end("Not Found");
});

// --- WebSocket bridge for Twilio <Connect><Stream> ---
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

wss.on("connection", (twilioWS) => {
  console.log("✅ Twilio connected to /media-stream");

  const oaWS = new WebSocket(
    `wss://api.openai.com/v1/realtime?model=${encodeURIComponent(MODEL)}`,
    { headers: { Authorization: `Bearer ${OPENAI_API_KEY}` } }
  );

  let streamSid = null;

  oaWS.on("open", () => {
    console.log("✅ OpenAI Realtime connected");
    oaWS.send(
      JSON.stringify({
        type: "session.update",
        session: {
          instructions:
            "You are the Westside Current tipline reporter. Collect who/what/when/where/how, ask 2–3 follow-ups, avoid legal advice, then read back a one-paragraph summary for confirmation.",
          modalities: ["audio"],
          turn_detection: { type: "server_vad" },
          input_audio_format: { type: "audio/pcmu", sample_rate_hz: 8000 },
          output_audio_format: { type: "audio/pcmu", sample_rate_hz: 8000 },
          voice: "alloy"
        }
      })
    );
  });

  // OpenAI -> Twilio (AI speaks)
  oaWS.on("message", (buf) => {
    try {
      const msg = JSON.parse(buf.toString());
      if (msg.type === "response.output_audio.delta" && msg.delta) {
        twilioWS.send(
          JSON.stringify({
            event: "media",
            streamSid,
            media: { payload: msg.delta }
          })
        );
      }
    } catch (e) {
      console.error("OpenAI message parse error:", e);
    }
  });

  // Twilio -> OpenAI (caller audio)
  twilioWS.on("message", (buf) => {
    try {
      const data = JSON.parse(buf.toString());
      if (data.event === "start") {
        streamSid = data.start.streamSid;
        console.log("Twilio stream started:", streamSid);
      } else if (data.event === "media" && data.media?.payload) {
        oaWS.send(
          JSON.stringify({
            type: "input_audio_buffer.append",
            audio: data.media.payload
          })
        );
      } else if (data.event === "stop") {
        if (oaWS.readyState === WebSocket.OPEN) oaWS.close();
      }
    } catch (e) {
      console.error("Twilio message parse error:", e);
    }
  });

  twilioWS.on("close", () => {
    if (oaWS.readyState === WebSocket.OPEN) oaWS.close();
    console.log("❌ Twilio disconnected");
  });

  oaWS.on("close", () => console.log("❌ OpenAI Realtime closed"));
  oaWS.on("error", (e) => console.error("OpenAI WS error:", e));
});

server.listen(PORT, "0.0.0.0", () => {
  console.log(`🚀 Relay listening on ${PORT}`);
});
