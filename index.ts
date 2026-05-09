import type { OpenClawPluginApi } from "openclaw/plugin-sdk";
import * as fs from "fs";
import * as path from "path";
import { execFileSync } from "child_process";
import { fileURLToPath } from "url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const RAW_DIR = "/home/openclaw/.openclaw/workspace/memory/raw";

// IST timezone helper
const IST_OPTIONS: Intl.DateTimeFormatOptions = {
  timeZone: 'Asia/Kolkata',
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
  hour12: false
};

const getISTDateString = (): string => {
  return new Date().toLocaleString('en-CA', { ...IST_OPTIONS, year: 'numeric', month: '2-digit', day: '2-digit' }).split(',')[0];
};

const getISTTimeString = (): string => {
  const now = new Date();
  // Use toLocaleString with explicit format parts, then extract time
  // en-CA format is: YYYY-MM-DD, HH:mm:ss - we extract the time portion
  const parts = new Intl.DateTimeFormat('en-CA', IST_OPTIONS).formatToParts(now);
  const hour = parts.find(p => p.type === 'hour')?.value || '00';
  const minute = parts.find(p => p.type === 'minute')?.value || '00';
  const second = parts.find(p => p.type === 'second')?.value || '00';
  return `${hour}:${minute}:${second}`;
};

// Full IST timestamp for logging (YYYY-MM-DD HH:mm:ss IST)
const getISTTimestamp = (): string => {
  const now = new Date();
  const parts = new Intl.DateTimeFormat('en-CA', IST_OPTIONS).formatToParts(now);
  const year = parts.find(p => p.type === 'year')?.value || '0000';
  const month = parts.find(p => p.type === 'month')?.value || '00';
  const day = parts.find(p => p.type === 'day')?.value || '00';
  const hour = parts.find(p => p.type === 'hour')?.value || '00';
  const minute = parts.find(p => p.type === 'minute')?.value || '00';
  const second = parts.find(p => p.type === 'second')?.value || '00';
  return `${year}-${month}-${day} ${hour}:${minute}:${second} IST`;
  return `${hour}:${minute}:${second}`;
};

const tmrPlugin = {
  id: "true-memory-recall",
  name: "True Memory Recall",
  description: "Captures webchat conversations to daily markdown files",
  kind: "memory" as const,

  register(api: OpenClawPluginApi) {
    api.logger.info(`[TMR] [${getISTTimestamp()}] Plugin registered`);

    // Ensure directory exists
    fs.mkdirSync(RAW_DIR, { recursive: true });

    // ===== CAPTURE: message_received (user messages - ALL channels) =====
    api.on("message_received", async (event, ctx) => {
      // Capture from ALL channels: webchat, discord, telegram, phone, etc.
      const channelId = ctx.channelId || "unknown";
      const content = typeof event.content === 'string'
        ? event.content
        : JSON.stringify(event.content);

      // Log which channel we're capturing from
      if (channelId !== "webchat") {
        api.logger.info(`[TMR] [${getISTTimestamp()}] Capturing from channel: ${channelId}`);
      }
      
      // Skip if too short
      if (!content || content.length < 10) return;
      
      // Skip filtered messages
      if (/^(hi|ok|okay|yes|no|yep|nah|hm|hmm|hey|yo|test|testing)$/i.test(content.trim())) {
        return;
      }
      
      const today = getISTDateString();
      const rawFile = path.join(RAW_DIR, `${today}.md`);
      const timestamp = getISTTimeString();
      
      // Clean content
      let cleanContent = content
        .replace(/<relevant-memories>[\s\S]*?<\/relevant-memories>\s*/g, "")
        .replace(/^Sender \(untrusted metadata\):[\s\S]*?(?=\n[A-Z])/m, "")
        .trim();
      
      if (!cleanContent) return;
      
      const line = `[${timestamp}] User: ${cleanContent.substring(0, 2000)}\n`;
      
      try {
        fs.appendFileSync(rawFile, line, "utf8");
        api.logger.info(`[TMR] [${getISTTimestamp()}] Captured user message`);
      } catch (err) {
        api.logger.warn(`[TMR] [${getISTTimestamp()}] Write failed: ${err}`);
      }
    });

    // ===== CAPTURE: agent_end (assistant responses) =====
    api.on("agent_end", async (event, ctx) => {
      if (!event.success || !event.messages?.length) return;
      
      // Only main sessions, not subagents
      const sessionKey = ctx.sessionKey || "";
      if (!sessionKey.includes("main")) return;
      
      const today = getISTDateString();
      const rawFile = path.join(RAW_DIR, `${today}.md`);
      
      // Get last assistant message
      const assistantMsgs = event.messages.filter((m: any) => m.role === "assistant");
      if (assistantMsgs.length === 0) return;
      
      const lastMsg = assistantMsgs[assistantMsgs.length - 1] as any;
      
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
      
      const timestamp = getISTTimeString();
      const line = `[${timestamp}] Liz: ${content.substring(0, 2000)}\n`;
      
      try {
        fs.appendFileSync(rawFile, line, "utf8");
        api.logger.info(`[TMR] [${getISTTimestamp()}] Captured assistant response`);
      } catch (err) {
        api.logger.warn(`[TMR] [${getISTTimestamp()}] Write failed: ${err}`);
      }
    });

    // ===== RECALL: before_agent_start =====
    api.on("before_agent_start", async (event, ctx) => {
      if (!event.prompt || event.prompt.length < 5) return;
      
      // Extract actual user message from prompt (remove ALL system metadata)
      let cleanQuery = event.prompt;
      
      // Strategy 1: Find the last timestamp line [Day YYYY-MM-DD HH:MM UTC]
      // The actual user message always follows this pattern
      const timestampRegex = /\[\w{3}\s+\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}\s+UTC\]\s*/g;
      let lastMatch: RegExpExecArray | null = null;
      let match: RegExpExecArray | null;
      while ((match = timestampRegex.exec(event.prompt)) !== null) {
        lastMatch = match;
      }
      
      if (lastMatch) {
        cleanQuery = event.prompt.substring(lastMatch.index + lastMatch[0].length).trim();
      } else {
        // Strategy 2: Remove Sender metadata block if present
        const senderEnd = event.prompt.indexOf('```\n\n[');
        if (senderEnd !== -1) {
          const afterSender = event.prompt.substring(senderEnd + 4);
          const lines = afterSender.split('\n');
          if (lines.length > 0) {
            // First line after sender block should be the timestamp line
            // The actual message is on the same line or next
            const firstLine = lines[0];
            const tsMatch = firstLine.match(/^\[\w{3}\s+\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}\s+UTC\]\s*(.*)$/);
            if (tsMatch) {
              cleanQuery = tsMatch[1] || lines.slice(1).join('\n').trim();
            } else {
              cleanQuery = afterSender.trim();
            }
          }
        }
      }
      
      // Final cleanup: remove any remaining system artifacts
      cleanQuery = cleanQuery
        .replace(/^Sender\s+\(untrusted metadata\):.*$/gims, '')
        .replace(/^```json\s*\{[\s\S]*?\}\s*```$/gims, '')
        .trim();
      
      const queryPreview = cleanQuery.substring(0, 100).replace(/\n/g, ' ');
      api.logger.info(`[TMR] ===========================================`);
      api.logger.info(`[TMR] USER QUERY: "${queryPreview}${cleanQuery.length > 100 ? '...' : ''}"`);
      api.logger.info(`[TMR] ===========================================`);
      
      try {
        // Call Python injector to get relevant context
        const pluginDir = path.dirname(__filename);
        const pythonScript = path.join(pluginDir, '..', 'src', 'plugin.py');
        
        // Use execFileSync with array args to prevent shell injection completely
        // Pass cleanQuery (actual user message) NOT event.prompt (with metadata)
        const result = execFileSync(
          '/home/linuxbrew/.linuxbrew/bin/python3',
          [pythonScript, '--inject', cleanQuery],
          { encoding: 'utf8', timeout: 5000 }
        );
        
        const context = result.trim();
        
        if (context && context.length > 0) {
          // Simple memory count and logging (narrative format, no triple parsing)
          const memoryCount = (context.match(/^\d+\./gm) || []).length;
          api.logger.info(`[TMR] [${getISTTimestamp()}] Found ${memoryCount} memories, injected ${context.length} chars`);
          
          // Save injection to file for visibility (in plugin logs dir)
          const pluginDir = path.dirname(__filename);
          const logsDir = path.join(pluginDir, '..', 'logs');
          fs.mkdirSync(logsDir, { recursive: true });
          const injectionLogFile = path.join(logsDir, 'last_injection.md');
          const istNow = new Date().toLocaleString('en-IN', { timeZone: 'Asia/Kolkata', dateStyle: 'full', timeStyle: 'long' });
          const injectionLog = `# Last TMR Injection - ${istNow}\n\n## Query\n${event.prompt.substring(0, 200)}...\n\n## Injected Context\n\n${context}\n`;
          try {
            fs.writeFileSync(injectionLogFile, injectionLog, 'utf8');
          } catch (e) {
            // Ignore write errors
          }
          
          return { prependContext: context };
        } else {
          api.logger.info(`[TMR] [${getISTTimestamp()}] No relevant memory found`);
          
          // Save "no memory" state (in plugin logs dir)
          const pluginDir = path.dirname(__filename);
          const logsDir = path.join(pluginDir, '..', 'logs');
          fs.mkdirSync(logsDir, { recursive: true });
          const injectionLogFile = path.join(logsDir, 'last_injection.md');
          const istNow = new Date().toLocaleString('en-IN', { timeZone: 'Asia/Kolkata', dateStyle: 'full', timeStyle: 'long' });
          const injectionLog = `# Last TMR Injection - ${istNow}\n\n## Query\n${event.prompt.substring(0, 200)}...\n\n## Result\nNo relevant memory found.\n`;
          try {
            fs.writeFileSync(injectionLogFile, injectionLog, 'utf8');
          } catch (e) {}
          
          return { prependContext: "[TMR: No relevant memory found]" };
        }
      } catch (err) {
        api.logger.warn(`[TMR] [${getISTTimestamp()}] Injection failed: ${err}`);
        return { prependContext: "[TMR: Memory search failed]" };
      }
    });

    // ===== COMPACTION: before_compaction (extract in-session conversations) =====
    api.on("before_compaction", async (event, ctx) => {
      const sessionKey = ctx.sessionKey || "";
      api.logger.info(`[TMR] [${getISTTimestamp()}] Compaction triggered for session: ${sessionKey}`);

      try {
        // Run incremental extractor on unprocessed raw files
        // This extracts any new/changed conversations BEFORE they get compacted away
        const pluginDir = path.dirname(__filename);
        const extractorScript = path.join(pluginDir, '..', 'scripts', 'incremental_extractor.py');

        // Fire-and-forget: don't block compaction, run in background
        // The incremental extractor uses hash tracking, so it only processes what's new
        const child = require('child_process').spawn(
          '/home/linuxbrew/.linuxbrew/bin/python3',
          [extractorScript],
          {
            detached: true,
            stdio: ['ignore', 'pipe', 'pipe']
          }
        );

        let stdout = '';
        let stderr = '';
        child.stdout?.on('data', (data: Buffer) => { stdout += data.toString(); });
        child.stderr?.on('data', (data: Buffer) => { stderr += data.toString(); });

        child.on('exit', (code: number | null) => {
          if (code === 0) {
            const summaryMatch = stdout.match(/Files: (\d+)[\s\S]*?Relations: (\d+)/);
            if (summaryMatch) {
              api.logger.info(
                `[TMR] [${getISTTimestamp()}] Incremental extraction complete: ${summaryMatch[1]} files, ${summaryMatch[2]} relations`
              );
            } else {
              api.logger.info(`[TMR] [${getISTTimestamp()}] Incremental extraction complete (no new files)`);
            }
          } else {
            api.logger.warn(`[TMR] [${getISTTimestamp()}] Extraction exited with code ${code}: ${stderr}`);
          }
        });

        child.unref();

      } catch (err) {
        api.logger.warn(`[TMR] [${getISTTimestamp()}] Compaction extraction failed: ${err}`);
      }
    });

    // ===== COMPACTION: after_compaction (log cleanup if needed) =====
    api.on("after_compaction", async (event, ctx) => {
      api.logger.info(`[TMR] [${getISTTimestamp()}] Compaction complete for session: ${ctx.sessionKey || 'unknown'}`);
    });

    api.registerService({
      id: "true-memory-recall",
      start: () => { api.logger.info(`[TMR] [${getISTTimestamp()}] Service started`); },
      stop: () => { api.logger.info(`[TMR] [${getISTTimestamp()}] Service stopped`); },
    });
  },
};

export default tmrPlugin;
