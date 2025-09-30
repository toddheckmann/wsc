import http from "http";
import { WebSocketServer } from "ws";

const PORT = Number(process.env.PORT || 5050);

// --- HTTP server: log EVERY request, always 200 JSON so /health can't 404 ---
const server = http.createServer((req, res) => {
  console.log(`HTTP ${req.method} ${req.url}`);
  res.writeHead(200, { "content-type": "application/json" });
  res.end(JSON.stringify({ ok: true, path: req.url, service: "diag" }));
});

// --- WS server: accept ONLY /media-stream and log the upgrade ---
const wss = new WebSocketServer({ noServer: true, perMessageDeflate: false });

server.on("upgrade", (req, socket, head) => {
  console.log(`UPGRADE ${req.url}`);
  if (!req.url || !req.url.startsWith("/media-stream")) {
    socket.destroy();
    return;
  }
  wss.handleUpgrade(req, socket, head, (ws) => {
    wss.emit("connection", ws, req);
  });
});

wss.on("connection", (ws, req) => {
  console.log(`✅ WS CONNECTED ${req.url}`);
  // keepalive
  const ping = setInterval(() => {
    if (ws.readyState === ws.OPEN) ws.ping();
  }, 15000);
  ws.on("message", (msg) => console.log(`WS MESSAGE ${msg?.length || 0}B`));
  ws.on("close", () => {
    clearInterval(ping);
    console.log("❌ WS CLOSED");
  });
});

server.listen(PORT, "0.0.0.0", () => {
  console.log(`🚀 DIAG server listening on ${PORT}`);
});
