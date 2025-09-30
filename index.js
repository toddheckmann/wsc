import http from "http";
import { WebSocketServer } from "ws";

const PORT = Number(process.env.PORT || 5050);

const server = http.createServer((req, res) => {
  if (req.url === "/health") {
    res.writeHead(200, { "content-type": "application/json" });
    return res.end(JSON.stringify({ ok: true, service: "ws-echo" }));
  }
  res.writeHead(404, { "content-type": "text/plain" });
  res.end("Not Found");
});

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
  ws.on("message", (msg) => {
    console.log("↔️  got message len:", msg?.length || 0);
    ws.send(JSON.stringify({ ok: true, echoBytes: msg.length || 0 }));
  });
});

server.listen(PORT, "0.0.0.0", () => {
  console.log(`🚀 WS echo listening on ${PORT}`);
});
