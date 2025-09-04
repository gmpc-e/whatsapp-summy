export function normalizeEvents(msgs, { chatTitles, contactNames } = {}) {
  const events = [];
  for (const m of (msgs || [])) {
    const jid = m?.key?.remoteJid || "";
    const isGroup = jid.endsWith("@g.us");
    const title = (chatTitles && chatTitles.get(jid)) || "";

    const text =
      m?.message?.conversation ??
      m?.message?.extendedTextMessage?.text ??
      m?.message?.imageMessage?.caption ??
      m?.message?.videoMessage?.caption ??
      m?.message?.documentMessage?.caption ?? "";

    const hasMedia = Boolean(
      m?.message?.imageMessage ||
      m?.message?.videoMessage ||
      m?.message?.audioMessage ||
      m?.message?.documentMessage ||
      m?.message?.stickerMessage
    );

    if (!text && !hasMedia) continue;

    const senderJid = m?.key?.participant || m?.key?.remoteJid || "";
    const senderName = (contactNames && contactNames.get(senderJid)) || "";

    events.push({
      type: "message",
      chat: { jid, title, type: isGroup ? "group" : "dm" },
      msg: {
        id: m?.key?.id || "",
        ts: (m?.messageTimestamp || 0) * 1000,
        sender: { jid: senderJid, name: senderName },
        text: text || "",
        has_media: hasMedia,
        reply_to: m?.message?.extendedTextMessage?.contextInfo?.stanzaId || null,
        links: []
      }
    });
  }
  return events;
}
