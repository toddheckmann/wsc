import Fastify from "fastify";
import fastifyWS from "@fastify/websocket";
import fastifyForm from "@fastify/formbody";
import WebSocket from "ws";
import { request } from "undici";
import dotenv from "dotenv";
dotenv.config();

const {
  OPENAI_API_KEY,
  OPENAI_REALTIME_MODEL = "gpt-4o-realtime-preview",
  PORT = process.env.PORT || 5050,
  // optional for post-call transcription
  TWILIO_ACCOUNT_SID,
  TWILIO_AUTH_TOKEN,
  SLACK_WEBHOOK_URL
} = process.env;

if (!OPENAI_API_KEY) {
  console.error("❌ Set OPENAI_API_KEY in your environment");
  process.exit(1);
}

const app = Fastify();
await app.register(fastifyWS);
await app.register(fastifyForm);

// ---------- Health check ----------
app.get("/", async () => ({ ok: true }));

// ---------- Twilio <Connect><Stream> WebSocket bridge ----------
app.get("/media-stream", { websocket: true }, (twilioWS /*, req */) => {
  console.log("✅ Twilio connected to /media-stream");

  // Connect to OpenAI Realtime (audio)
  const oaWS = new WebSocket(
    `wss://api.openai.com/v1/realtime?model=${encodeURIComponent(
      OPENAI_REALTIME_MODEL
    )}`,
    { headers: { Authorization: `Bearer ${OPENAI_API_KEY}` } }
  );

  let streamSid = null;

  oaWS.on("open", () => {
    console.log("✅ OpenAI Realtime connected");
    // Configure session: μ-law 8k both directions to match Twilio
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

  // OpenAI → Twilio (AI's audio back to caller)
  oaWS.on("message", (buf) => {
    try {
      const msg = JSON.parse(buf.toString());
      if (msg.type === "response.output_audio.delta" && msg.delta) {
        const frame = {
          event: "media",
          streamSid,
          media: { payload: msg.delta } // base64 PCMU
        };
        twilioWS.send(JSON.stringify(frame));
      }
    } catch (e) {
      console.error("OpenAI message parse error:", e);
    }
  });

  // Twilio → OpenAI (caller audio to model)
  twilioWS.on("message", (buf) => {
    try {
      const data = JSON.parse(buf.toString());
      if (data.event === "start") {
        streamSid = data.start.streamSid;
        console.log("Twilio stream started:", streamSid);
      } else if (data.event === "media" && data.media?.payload) {
        oaWS.send(
          JS
