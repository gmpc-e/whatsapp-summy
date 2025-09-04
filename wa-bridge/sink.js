import axios from "axios";
import jwt from "jsonwebtoken";

export async function postBatch(url, secret, payload) {
  const token = jwt.sign({ sub: "wa-bridge", aud: "ingest" }, secret, { expiresIn: "120s" });
  await axios.post(url, payload, {
    headers: { Authorization: `Bearer ${token}` },
    timeout: 10000
  });
}
