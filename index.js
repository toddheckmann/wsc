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

// Health check
app.get("/", async () => ({ ok: true }));

// Twilio <Connect><Stream> WebSocket bridge
app.get("/media-stream", { websocket: true }, (twilioWS) => {
  console.log("✅ Twilio connected to /media-stream");

  const oaWS = new WebSocket(
    `wss://api.openai.com/v1/realtime?model=${encodeURIComponent(
      OPENAI_REALTIME_MODEL
    )}`,
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

  // OpenAI -> Twilio (AI audio)
  oaWS.on("message", (buf) => {
    try {
      const msg = JSON.parse(buf.toString());
      if (msg.type === "response.output_audio.delta" && msg.delta) {
        const frame = {
          event: "media",
          streamSid,
          media: { payload: msg.delta }
        };
        twilioWS.send(JSON.stringify(frame));
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

// (Optional) Recording callback -> transcription + Slack
app.post("/recording-callback", async (req, reply) => {
  try {
    const {
      RecordingUrl,
      RecordingSid,
      CallSid,
      RecordingStatus,
      RecordingDuration
    } = req.body || {};

    if (!RecordingUrl || RecordingStatus !== "completed") {
      return reply.send({ ok: true });
    }

    const mediaUrl = `${RecordingUrl}.mp3`;
    const res = await request(mediaUrl, {
      method: "GET",
      headers:
        TWILIO_ACCOUNT_SID && TWILIO_AUTH_TOKEN
          ? {
              Authorization:
                "Basic " +
                Buffer.from(
                  `${TWILIO_ACCOUNT_SID}:${TWILIO_AUTH_TOKEN}`
                ).toString("base64")
            }
          : {}
    });
    const audioBuffer = Buffer.from(await res.body.arrayBuffer());

    const form = new FormData();
    form.append("file", new Blob([audioBuffer], { type: "audio/mpeg" }), "rec.mp3");
    form.append("model", "gpt-4o-mini-transcribe");

    const tr = await fetch("https://api.openai.com/v1/audio/transcriptions", {
      method: "POST",
      headers: { Authorization: `Bearer ${OPENAI_API_KEY}` },
      body: form
    });
    const trJson = await tr.json();

    if (SLACK_WEBHOOK_URL) {
      const text = `*Tip transcript ready*\n• CallSid: ${CallSid}\n• RecordingSid: ${RecordingSid}\n• Duration: ${RecordingDuration}s\n\n${(trJson.text || "").slice(
        0,
        4000
      )}`;
      await fetch(SLACK_WEBHOOK_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text })
      });
    }

    return reply.send({ ok: true, RecordingSid });
  } catch (e) {
    console.error("/recording-callback error", e);
    return reply.code(500).send({ ok: false, error: String(e) });
  }
});

app.listen({ port: Number(PORT), host: "0.0.0.0" }, () => {
  console.log(`🚀 Relay server running on ${PORT}`);
});
