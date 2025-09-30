import http from "http";
import { WebSocketServer } from "ws";

const PORT = Number(process.env.PORT || 5050);

// Basic HTTP for health checks
const server = http.createServer((req, res) => {
  if (req.url === "/health") {
    res.writeHead(200, { "content-type": "application/json" });
    return res.end(JSON.stringify({ ok: true, service: "ws-echo" }));
  }
  res.writeHead(404, { "content-type": "text/plain" });
  res.end("Not Found");
});

// WebSocket server (no deps) – accept only /media-stream
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

wss.on("connection", (ws, req) => {
  console.log("✅ WS client connected:", req.url);

  // Keepalive
  const pinger = setInterval(() => {
    if (ws.readyState === ws.OPEN) ws.ping();
  }, 15000);

  ws.on("message", (msg) => {
    console.log("↔️  got message len:", msg?.length || 0);
    // Echo back a tiny JSON so you can see it in the browser if using a test client
    try {
      ws.send(JSON.stringify({ ok: true, echoBytes: msg.length || 0 }));
    } catch {}
  });

  ws.on("close", () => {
    clearInterval(pinger);
    console.log("❌ WS client closed");
  });
});

server.listen(PORT, "0.0.0.0", () => {
  console.log(`🚀 WS echo listening on ${PORT}`);
});
