wss.on("connection", (twilioWS) => {
  console.log("✅ Twilio connected to /media-stream");

  const oaWS = new WebSocket(
    `wss://api.openai.com/v1/realtime?model=${encodeURIComponent(MODEL)}`,
    { headers: { Authorization: `Bearer ${OPENAI_API_KEY}` } }
  );

  let streamSid = null;
  let oaReady = false;
  const pending = [];              // queue of base64 PCMU frames

  const sendToOA = (b64) => {
    if (!oaReady || oaWS.readyState !== WebSocket.OPEN) {
      pending.push(b64);
      return;
    }
    oaWS.send(JSON.stringify({
      type: "input_audio_buffer.append",
      audio: b64
    }));
  };

  oaWS.on("open", () => {
    console.log("✅ OpenAI Realtime connected");
    // configure audio formats + behavior
    oaWS.send(JSON.stringify({
      type: "session.update",
      session: {
        instructions:
          "You are the Westside Current tipline reporter. Collect who/what/when/where/how, ask 2–3 follow-ups, avoid legal advice, then read back a one-paragraph summary for confirmation.",
        modalities: ["audio"],
        turn_detection: { type: "server_vad" },
        input_audio_format:  { type: "audio/pcmu", sample_rate_hz: 8000 },
        output_audio_format: { type: "audio/pcmu", sample_rate_hz: 8000 },
        voice: "alloy"
      }
    }));
    oaReady = true;
    // flush any queued frames
    while (pending.length && oaWS.readyState === WebSocket.OPEN) {
      const frame = pending.shift();
      oaWS.send(JSON.stringify({ type: "input_audio_buffer.append", audio: frame }));
    }
  });

  // AI -> caller (audio back to Twilio)
  oaWS.on("message", (buf) => {
    try {
      const msg = JSON.parse(buf.toString());
      if (msg.type === "response.output_audio.delta" && msg.delta) {
        twilioWS.send(JSON.stringify({
          event: "media",
          streamSid,
          media: { payload: msg.delta }  // base64 PCMU
        }));
      }
    } catch (e) {
      console.error("OpenAI message parse error:", e);
    }
  });

  // Caller -> AI
  twilioWS.on("message", (buf) => {
    try {
      const data = JSON.parse(buf.toString());
      if (data.event === "start") {
        streamSid = data.start.streamSid;
        console.log("Twilio stream started:", streamSid);
      } else if (data.event === "media" && data.media?.payload) {
        sendToOA(data.media.payload);      // <-- uses buffer-aware sender
      } else if (data.event === "stop") {
        if (oaWS.readyState === WebSocket.OPEN) oaWS.close(1000, "call ended");
      }
    } catch (e) {
      console.error("Twilio message parse error:", e);
    }
  });

  // cleanup
  twilioWS.on("close", () => {
    if (oaWS.readyState === WebSocket.OPEN) oaWS.close(1000, "twilio socket closed");
    console.log("❌ Twilio disconnected");
  });
  oaWS.on("close", () => console.log("❌ OpenAI Realtime closed"));
  oaWS.on("error", (e) => console.error("OpenAI WS error:", e));
});
