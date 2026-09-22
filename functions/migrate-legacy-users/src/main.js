import { Client, Query, TablesDB, Users } from "node-appwrite";

const SOURCE_DATABASE_ID = "default";
const SOURCE_TABLE_ID = "users";
const TARGET_DATABASE_ID = "6a840e69001dca03b9d4";
const TARGET_TABLE_ID = "learner_staate";
const STATE_KEYS = [
  "user", "watchlists", "alerts", "portfolio", "positions", "trades",
  "journal", "learning", "notifications", "orders", "cash_flows",
];

function decodeFirestore(value) {
  if (Array.isArray(value)) return value.map(decodeFirestore);
  if (!value || typeof value !== "object") return value;
  if ("stringValue" in value) return value.stringValue;
  if ("integerValue" in value) return Number(value.integerValue);
  if ("doubleValue" in value) return Number(value.doubleValue);
  if ("booleanValue" in value) return Boolean(value.booleanValue);
  if ("nullValue" in value) return null;
  if ("timestampValue" in value) return value.timestampValue;
  if ("arrayValue" in value) {
    const values = value.arrayValue.values || [];
    return (Array.isArray(values) ? values : Object.values(values)).map(decodeFirestore);
  }
  if ("mapValue" in value) return decodeFirestore(value.mapValue.fields || {});
  if ("fields" in value) return decodeFirestore(value.fields);
  return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, decodeFirestore(item)]));
}

function readLegacyValue(value) {
  let parsed = value;
  // The Firebase migration stores some nested maps as JSON inside a JSON
  // string. Unwrap up to three layers without touching ordinary text fields.
  for (let index = 0; index < 3 && typeof parsed === "string"; index += 1) {
    try {
      parsed = JSON.parse(parsed);
    } catch {
      break;
    }
  }
  return decodeFirestore(parsed);
}

function extractLegacyState(row) {
  const state = {};
  for (const key of STATE_KEYS) {
    if (row[key] !== undefined && row[key] !== null) state[key] = readLegacyValue(row[key]);
  }
  return state;
}

function emailFromState(state) {
  const user = state.user || {};
  const direct = String(user.email || user.profile?.email || "").trim().toLowerCase();
  if (direct.includes("@")) return direct;
  const queue = [user];
  while (queue.length) {
    const value = queue.shift();
    if (!value || typeof value !== "object") continue;
    for (const [key, item] of Object.entries(value)) {
      if (key.toLowerCase() === "email" && typeof item === "string" && item.includes("@")) {
        return item.trim().toLowerCase();
      }
      if (item && typeof item === "object") queue.push(item);
    }
  }
  return "";
}

async function listAllRows(tablesDB, databaseId, tableId) {
  const rows = [];
  let offset = 0;
  while (true) {
    const page = await tablesDB.listRows({
      databaseId,
      tableId,
      queries: [Query.limit(100), Query.offset(offset)],
      total: false,
      ttl: 0,
    });
    const batch = page.rows || [];
    rows.push(...batch);
    if (batch.length < 100) return rows;
    offset += batch.length;
  }
}

export default async ({ req, res, log, error }) => {
  const mode = String(req.body || "dry-run").trim().toLowerCase();
  if (!["dry-run", "apply"].includes(mode)) {
    return res.json({ error: "Use request body 'dry-run' or 'apply'." }, 400);
  }

  const client = new Client()
    .setEndpoint(process.env.APPWRITE_FUNCTION_API_ENDPOINT)
    .setProject(process.env.APPWRITE_FUNCTION_PROJECT_ID)
    // Appwrite supplies a short-lived, function-only admin key for every
    // execution. It is intentionally delivered in this header at runtime.
    .setKey(req.headers["x-appwrite-key"]);
  const tablesDB = new TablesDB(client);
  const users = new Users(client);
  const legacyRows = await listAllRows(tablesDB, SOURCE_DATABASE_ID, SOURCE_TABLE_ID);
  const report = { mode, scanned: legacyRows.length, matched: 0, migrated: 0, skipped: [], errors: [] };

  for (const legacyRow of legacyRows) {
    try {
      const state = extractLegacyState(legacyRow);
      const email = emailFromState(state);
      if (!email) {
        report.skipped.push({ legacyRowId: legacyRow.$id, reason: "No email in legacy user data" });
        continue;
      }
      const matches = await users.list({ queries: [Query.equal("email", [email]), Query.limit(2)] });
      const account = (matches.users || [])[0];
      if (!account) {
        report.skipped.push({ legacyRowId: legacyRow.$id, email, reason: "User has not signed in to Appwrite yet" });
        continue;
      }
      report.matched += 1;
      if (mode === "apply") {
        state.user = { ...(state.user || {}), uid: account.$id, email: account.email };
        await tablesDB.upsertRow({
          databaseId: TARGET_DATABASE_ID,
          tableId: TARGET_TABLE_ID,
          rowId: account.$id,
          data: { payload: JSON.stringify(state) },
          permissions: [`read(\"user:${account.$id}\")`, `update(\"user:${account.$id}\")`],
        });
        report.migrated += 1;
      }
    } catch (cause) {
      error(`Legacy row ${legacyRow.$id}: ${cause.message || String(cause)}`);
      report.errors.push({ legacyRowId: legacyRow.$id, reason: cause.message || String(cause) });
    }
  }
  log(JSON.stringify(report));
  return res.json(report);
};
