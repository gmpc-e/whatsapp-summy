import makeWASocket, {
  useMultiFileAuthState,
  Browsers,
  fetchLatestBaileysVersion
} from "@whiskeysockets/baileys";
import pino from "pino";
import dotenv from "dotenv";
import { normalizeEvents } from "./normalize.js";
import { postBatch } from "./sink.js";
import qrcode from "qrcode-terminal";

dotenv.config();

const log = pino({ level: "info" });
const BRIDGE_ID = process.env.BRIDGE_ID || "macbook-elad";
const FLUSH_MS = Number(process.env.FLUSH_MS || 1500);
const BATCH_SIZE = Number(process.env.BATCH_SIZE || 200);
const BACKEND_INGEST = process.env.BACKEND_INGEST || "http://127.0.0.1:8000/ingest/wa";
const JWT_SECRET = process.env.JWT_SECRET;
const chatTitles = new Map();   // jid -> title
const contactNames = new Map(); // jid -> name

if (!JWT_SECRET) {
  log.error("JWT_SECRET missing (set in .env)");
  process.exit(1);
}

let buffer = [];
let flushTimer = null;

async function flush() {
  if (!buffer.length) return;
  const events = buffer.splice(0, buffer.length);
  try {
    await postBatch(BACKEND_INGEST, JWT_SECRET, {
      bridge_id: BRIDGE_ID,
      ts: Date.now(),
      events
    });
    log.info({ count: events.length }, "posted batch");
  } catch (e) {
    log.error({ err: e?.message }, "postBatch failed");
    // put them back to retry next tick
    buffer.unshift(...events);
  }
}

function scheduleFlush(immediate = false) {
  if (immediate || buffer.length >= BATCH_SIZE) return void flush();
  if (flushTimer) clearTimeout(flushTimer);
  flushTimer = setTimeout(flush, FLUSH_MS);
}

async function main() {
  const { version } = await fetchLatestBaileysVersion();
  const { state, saveCreds } = await useMultiFileAuthState("./auth");

const sock = makeWASocket({
  auth: state,
  browser: Browsers.macOS("Safari"),
  version,
  syncFullHistory: true,
  logger: pino({ level: "warn" })
});

// Listen for QR and connection updates
sock.ev.on("connection.update", (update) => {
  const { connection, qr } = update;
  if (qr) {
    console.log("🔗 Scan this QR code with WhatsApp:");
    qrcode.generate(qr, { small: true });
  }
  if (connection === "open") {
    console.log("✅ WhatsApp connection established");
  } else if (connection === "close") {
    console.log("❌ WhatsApp connection closed");
  }
});


  sock.ev.on("creds.update", saveCreds);

  // New / updated messages
sock.ev.on("messages.upsert", ({ messages }) => {
  const evts = normalizeEvents(messages, { chatTitles, contactNames });
  if (evts.length) {
    buffer.push(...evts);
    scheduleFlush();
  }
});

  // Optional: message updates (edits/deletes)
  sock.ev.on("messages.update", (updates) => {
    // For MVP we skip, but you can map to {type:"message_deleted"} if desired
  });

  // Sync initial history on first login (optional handling)
sock.ev.on("chats.upsert", (chs) => {
  for (const c of chs) {
    if (c?.id) chatTitles.set(c.id, c?.name || c?.subject || "");
  }
});
sock.ev.on("chats.update", (chs) => {
  for (const c of chs) {
    if (c?.id && (c?.name || c?.subject)) chatTitles.set(c.id, c.name || c.subject);
  }
});
sock.ev.on("contacts.upsert", (cts) => {
  for (const c of cts) {
    if (c?.id) contactNames.set(c.id, c?.name || c?.notify || "");
  }
});
sock.ev.on("contacts.update", (cts) => {
  for (const c of cts) {
    if (c?.id && (c?.name || c?.notify)) contactNames.set(c.id, c.name || c.notify);
  }
});


  // Graceful shutdown
  process.on("SIGINT", async () => {
    log.info("SIGINT received, flushing...");
    await flush();
    process.exit(0);
  });
  process.on("SIGTERM", async () => {
    log.info("SIGTERM received, flushing...");
    await flush();
    process.exit(0);
  });
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
