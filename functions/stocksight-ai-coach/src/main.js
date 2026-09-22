const NIM_ENDPOINT = "https://integrate.api.nvidia.com/v1/chat/completions";
const DEFAULT_MODEL = "nvidia/nemotron-3-ultra-550b-a55b";
const MAX_MESSAGE_COUNT = 12;
const MAX_MESSAGE_LENGTH = 20_000;

function jsonBody(req) {
  // Open Runtimes can provide the execution body already parsed.
  if (req?.body && typeof req.body === "object" && !Array.isArray(req.body)) {
    return req.body;
  }
  try {
    const parsed = JSON.parse(String(req.body || "{}"));
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch {
    return {};
  }
}

function safeMessages(value) {
  if (!Array.isArray(value)) return [];
  const safe = value.flatMap((message) => {
    const role = String(message?.role || "");
    const content = String(message?.content || "").trim();
    if (!content || !["system", "user", "assistant"].includes(role)) return [];
    return [{ role, content: content.slice(0, MAX_MESSAGE_LENGTH) }];
  });
  // NVIDIA chat templates accept one system instruction followed by normal
  // conversation turns. Preserve that instruction when trimming history.
  const system = safe.find((message) => message.role === "system");
  const conversation = safe.filter((message) => message.role !== "system").slice(-(MAX_MESSAGE_COUNT - (system ? 1 : 0)));
  return system ? [system, ...conversation] : conversation;
}

export default async ({ req, res, log, error }) => {
  if (req.method !== "POST") {
    return res.json({ detail: "Use POST for AI chat." }, 405);
  }

  // Appwrite adds this only when a signed-in project user executes a function
  // that grants execute access to users. Do not make this function executable
  // by guests or Any.
  const userId = String(req.headers["x-appwrite-user-id"] || "").trim();
  if (!userId) {
    return res.json({ detail: "Sign in to use the hosted AI coach." }, 401);
  }

  const apiKey = String(process.env.NVIDIA_NIM_API_KEY || "").trim();
  if (!apiKey) {
    error("NVIDIA_NIM_API_KEY is not configured.");
    return res.json({ detail: "The hosted AI coach is not configured yet." }, 503);
  }

  const body = jsonBody(req);
  const messages = safeMessages(body.messages);
  if (!messages.length) {
    return res.json({ detail: "No valid chat message was provided." }, 400);
  }

  // The model is deliberately chosen by the hosted function, not by a public
  // desktop request. This keeps an EXE update from changing the deployed cost
  // or safety profile.
  const model = DEFAULT_MODEL;
  const mode = String(body.mode || "chat").toLowerCase() === "analysis" ? "analysis" : "chat";
  try {
    const upstream = await fetch(NIM_ENDPOINT, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${apiKey}`,
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify({
        model,
        messages,
        temperature: 0.4,
        top_p: 0.95,
        max_tokens: mode === "analysis" ? 2200 : 900,
        stream: false,
        // A finished, source-cited JSON brief is more useful to StockSight
        // than hidden reasoning that can consume the whole response budget.
        chat_template_kwargs: { enable_thinking: false },
      }),
    });

    const upstreamBody = await upstream.json().catch(() => ({}));
    if (!upstream.ok) {
      error(`NVIDIA NIM request failed with status ${upstream.status}.`);
      return res.json({ detail: "The hosted AI coach could not answer right now." }, 502);
    }

    const message = upstreamBody?.choices?.[0]?.message || {};
    const reply = String(message.content || message.reasoning_content || "").trim();
    if (!reply) {
      return res.json({ detail: "The hosted AI coach returned an empty reply." }, 502);
    }

    log(`Hosted AI reply returned for user ${userId}.`);
    return res.json({ reply, model, mode });
  } catch (cause) {
    error(`NVIDIA NIM request failed: ${cause?.message || String(cause)}`);
    return res.json({ detail: "The hosted AI coach could not answer right now." }, 502);
  }
};
