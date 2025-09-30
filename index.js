wss.on("connection", (twilioWS) => {
  console.log("✅ Twilio connected to /media-stream");

  const oaWS = new WebSocket(
    `wss://api.openai.com/v1/realtime?model=${encodeURIComponent(MODEL)}`,
    {
      headers: {
        Authorization: `Bearer ${OPENAI_API_KEY}`,
        "OpenAI-Beta": "realtime=v1"          // 👈 add this
      }
    }
  );

  let streamSid = null;
  let oaReady = false;
  let sessionConfigured = false;
  const pending = [];
  let haveUncommittedAudio = false;
  let commitTimer = null;

  const startCommitTimer = () => {
    if (commitTimer) return;
    commitTimer = setInterval(() => {
      if (haveUncommittedAudio && oaWS.readyState === WebSocket.OPEN) {
        oaWS.send(JSON.stringify({ type: "input_audio_buffer.commit" })); // 👈 commit so model processes
        haveUncommittedAudio = false;
      }
    }, 700); // gentle cadence
  };

  const stopCommitTimer = () => {
    if (commitTimer) clearInterval(commitTimer);
    commitTimer = null;
  };

  const sendToOA = (b64) => {
    if (!oaReady || oaWS.readyState !== WebSocket.OPEN) {
      pending.push(b64);
      return;
    }
    oaWS.send(JSON.stringify({ type: "input_audio_buffer.append", audio: b64 }));
    haveUncommittedAudio = true;
    startCommitTimer();
  };

  oaWS.on("open", () => {
    console.log("✅ OpenAI Realtime connected");
    // Configure session (PCMU μ-law @ 8k) BEFORE any response
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
  });

  // Log all messages to catch errors / state
  oaWS.on("message", (buf) => {
    let msg;
    try { msg = JSON.parse(buf.toString()); } catch { return; }

    // Helpful debug:
    if (msg.type && msg.type !== "response.output_audio.delta") {
      console.log("OA evt:", msg.type);
      if (msg.error) console.log("OA error:", msg.error);
    }

    if (msg.type === "session.updated") {
      sessionConfigured = true;
      oaReady = true;
      // Flush queued frames
      while (pending.length && oaWS.readyState === WebSocket.OPEN) {
        const frame = pending.shift();
        oaWS.send(JSON.stringify({ type: "input_audio_buffer.append", audio: frame }));
        haveUncommittedAudio = true;
      }
      // Say hello once the session is truly configured
      oaWS.send(JSON.stringify({ type: "response.create" }));
      return;
    }

    // Model speaking → send frames back to Twilio
    if (msg.type === "response.output_audio.delta" && msg.delta) {
      if (streamSid) {
        twilioWS.send(JSON.stringify({
          event: "media",
          streamSid,
          media: { payload: msg.delta } // base64 PCMU
        }));
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
      } else if (data.event === "media" && data.media?.payload)
