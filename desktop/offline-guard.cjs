// Applied to MTranServer and inherited by its Node workers. No Internet sockets.
const net = require("node:net");
net.Socket.prototype.connect = function () {
  // Translation accepts inbound loopback requests; it needs no outbound sockets.
  throw new Error("Charlie offline mode blocks external connections");
};
globalThis.fetch = async () => { throw new Error("Charlie offline mode blocks remote downloads"); };
// Protect every route, including upstream compatibility/UI endpoints.
const http = require("node:http");
const emit = http.Server.prototype.emit;
const token = process.argv[process.argv.indexOf("--api-token") + 1];
http.Server.prototype.emit = function (event, ...args) {
  if (event === "request") {
    const [request, response] = args;
    if (!token || request.headers.host !== "127.0.0.1:8991" || request.headers.origin || request.headers.authorization !== "Bearer " + token) {
      response.writeHead(403, {"Content-Type":"application/json"});
      response.end('{"error":"Local authenticated access only"}');
      return true;
    }
  }
  return emit.call(this, event, ...args);
};
