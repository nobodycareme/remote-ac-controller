// broker-dev.cjs — Local MQTT broker (aedes) for closed-loop testing.
// Listens on 1883 (plaintext) and, if certs are present, 8883 (TLS, project CA).
// Auth is permissive for dev; the production broker enforces password + ACL.
'use strict';
const aedes = require('aedes')();
const net = require('net');
const tls = require('tls');
const fs = require('fs');
const path = require('path');

const TCP_PORT = parseInt(process.env.BROKER_TCP_PORT || '1883', 10);
const TLS_PORT = parseInt(process.env.BROKER_TLS_PORT || '8883', 10);
const CERT_DIR = path.resolve(__dirname, '../broker/certs');

const tcp = net.createServer(aedes.handle);
tcp.listen(TCP_PORT, () => console.log(`[broker-dev] TCP  mqtt://localhost:${TCP_PORT}`));

const keyPath = path.join(CERT_DIR, 'server.key');
const certPath = path.join(CERT_DIR, 'server.crt');
const caPath = path.join(CERT_DIR, 'ca.crt');
if (fs.existsSync(keyPath) && fs.existsSync(certPath)) {
  const tlsOpts = {
    key: fs.readFileSync(keyPath),
    cert: fs.readFileSync(certPath),
    ca: fs.existsSync(caPath) ? fs.readFileSync(caPath) : undefined,
    requestCert: false,
    rejectUnauthorized: false,
  };
  const tlsServer = tls.createServer(tlsOpts, (socket) => aedes.handle(socket));
  tlsServer.listen(TLS_PORT, () => console.log(`[broker-dev] TLS  mqtts://localhost:${TLS_PORT} (client validates via ca.crt)`));
} else {
  console.log(`[broker-dev] TLS skipped (no server cert in ${CERT_DIR})`);
}

aedes.on('clientError', (c, e) => console.log('[broker-dev] clientError', c.id, e.message));
aedes.on('publish', (p) => {
  if (p.topic.endsWith('/availability')) console.log(`[broker-dev] availability <- ${p.payload.toString()}`);
});
aedes.on('subscribe', (s, c) => console.log(`[broker-dev] ${c.id} subscribed ${s.map((x) => x.topic).join(',')}`));

console.log('[broker-dev] running. Ctrl+C to stop.');
