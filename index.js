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

// ---- Health check ----
app.get("/", async () => ({ ok: true }));

// ---- Twilio <Connect><Stream> WebSocket ----
app.get("/media-stream", { websocket: true }, (connection) => {
  console.log("✅ Twilio connected to /media-stream");

  const openAi = new WebSocket(
    `wss://api.openai.com/v1/realtime?model=${encodeURIComponent(
      OPENAI_REALTIME_MODEL
    )}`,
    { headers: { Authorization: `Bearer ${OPENAI_API_KEY}` } }
  );

  let streamSid = null;

  openAi.on("open", () => {
    console.log("✅ OpenAI Realtime connected");
    const sessionUpdate = {
      type: "session.update",
      session: {
        instructions:
          "You are the Westside Current tipline reporter. Collect who/what/when/where/how, ask 2–3 follow-ups, avoid legal advice, then read back a one-paragraph summary for confirmation.",
        modalities: ["audio"],
        turn_detection: { type:_
