import type { OpenClawPluginApi } from "openclaw/plugin-sdk";
import * as fs from "fs";
import * as path from "path";

const RAW_DIR = "/home/openclaw/.openclaw/workspace/memory/raw";

const tmrPlugin = {
  id: "true-memory-recall",
  name: "True Memory Recall",
  description: "Captures webchat conversations to daily markdown files",
  kind: "memory" as const,

  register(api: OpenClawPluginApi) {
    api.logger.info("[TMR] Plugin registered");

    // Ensure directory exists
    fs.mkdirSync(RAW_DIR, { recursive: true });

    // ===== CAPTURE: message_received (user messages) =====
    api.on("message_received", async (event, ctx) => {
      if (ctx.channelId !== "webchat") return;
      
      const content = typeof event.content === 'string' 
        ? event.content 
        : JSON.stringify(event.content);
      
      // Skip if too short
      if (!content || content.length < 10) return;
      
      // Skip filtered messages
      if (/^(hi|ok|okay|yes|no|yep|nah|hm|hmm|hey|yo|test|testing)$/i.test(content.trim())) {
        return;
      }
      
      const today = new Date().toISOString().slice(0, 10);
      const rawFile = path.join(RAW_DIR, `${today}.md`);
      const timestamp = new Date().toTimeString().slice(0, 8);
      
      // Clean content
      let cleanContent = content
        .replace(/<relevant-memories>[\s\S]*?<\/relevant-memories>\s*/g, "")
        .replace(/^Sender \(untrusted metadata\):[\s\S]*?(?=\n[A-Z])/m, "")
        .trim();
      
      if (!cleanContent) return;
      
      const line = `[${timestamp}] User: ${cleanContent.substring(0, 2000)}\n`;
      
      try {
        fs.appendFileSync(rawFile, line, "utf8");
        api.logger.info(`[TMR] Captured user message`);
      } catch (err) {
        api.logger.warn(`[TMR] Write failed: ${err}`);
      }
    });

    // ===== CAPTURE: agent_end (assistant responses) =====
    api.on("agent_end", async (event, ctx) => {
      if (!event.success || !event.messages?.length) return;
      
      // Only main sessions, not subagents
      const sessionKey = ctx.sessionKey || "";
      if (!sessionKey.includes("main")) return;
      
      const today = new Date().toISOString().slice(0, 10);
      const rawFile = path.join(RAW_DIR, `${today}.md`);
      
      // Get last assistant message
      const assistantMsgs = event.messages.filter((m: any) => m.role === "assistant");
      if (assistantMsgs.length === 0) return;
      
      const lastMsg = assistantMsgs[assistantMsgs.length - 1];
      
      let content = "";
      if (typeof lastMsg.content === "string") {
        content = lastMsg.content;
      } else if (Array.isArray(lastMsg.content)) {
        content = lastMsg.content
          .filter((b: any) => b.type === "text")
          .map((b: any) => b.text)
          .join("\n");
      }
      
      if (!content || content.length < 10) return;
      
      const timestamp = new Date().toTimeString().slice(0, 8);
      const line = `[${timestamp}] Liz: ${content.substring(0, 2000)}\n`;
      
      try {
        fs.appendFileSync(rawFile, line, "utf8");
        api.logger.info(`[TMR] Captured assistant response`);
      } catch (err) {
        api.logger.warn(`[TMR] Write failed: ${err}`);
      }
    });

    // ===== RECALL: before_agent_start =====
    api.on("before_agent_start", async (event, ctx) => {
      // TODO: Implement context injection from Qdrant
      // For now, just log
      if (event.prompt) {
        api.logger.info(`[TMR] before_agent_start: query length ${event.prompt.length}`);
      }
    });

    api.registerService({
      id: "true-memory-recall",
      start: () => { api.logger.info("[TMR] Service started"); },
      stop: () => { api.logger.info("[TMR] Service stopped"); },
    });
  },
};

export default tmrPlugin;
