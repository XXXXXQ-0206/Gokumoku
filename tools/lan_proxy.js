const net = require("net");

function arg(name, fallback) {
  const prefix = `--${name}=`;
  const found = process.argv.find((item) => item.startsWith(prefix));
  return found ? found.slice(prefix.length) : fallback;
}

const listenHost = arg("listen-host", "0.0.0.0");
const listenPort = Number(arg("listen-port", "18090"));
const targetHost = arg("target-host", "127.0.0.1");
const targetPort = Number(arg("target-port", "8090"));

const server = net.createServer((client) => {
  const upstream = net.connect({ host: targetHost, port: targetPort });

  client.pipe(upstream);
  upstream.pipe(client);

  const closeBoth = () => {
    client.destroy();
    upstream.destroy();
  };

  client.on("error", closeBoth);
  upstream.on("error", closeBoth);
  client.on("close", () => upstream.destroy());
  upstream.on("close", () => client.destroy());
});

server.listen(listenPort, listenHost, () => {
  console.log(`LAN proxy listening on ${listenHost}:${listenPort} -> ${targetHost}:${targetPort}`);
});

server.on("error", (error) => {
  console.error(error.message);
  process.exit(1);
});
