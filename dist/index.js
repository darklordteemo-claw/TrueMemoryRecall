"use strict";
/**
 * TrueMemoryRecall Plugin
 * TypeScript hooks with Python backend
 */
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function(o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
Object.defineProperty(exports, "__esModule", { value: true });
const child_process_1 = require("child_process");
const fs = __importStar(require("fs"));
const path = __importStar(require("path"));
const TMRPlugin = {
    init(api, config) {
        const cfg = config || {};
        const pythonPath = cfg.pythonPath || 'python3';
        const pluginDir = cfg.pluginDir || path.join(process.env.HOME || '', '.openclaw/extensions/TrueMemoryRecall');
        const rawDir = path.join(process.env.HOME || '', '.openclaw/workspace/memory/raw');
        // Ensure directory exists
        fs.mkdirSync(rawDir, { recursive: true });
        api.logger.info('[TMR] Plugin initialized');
        // AUTO-RECALL: Inject context before agent starts
        if (cfg.autoRecall !== false) {
            api.on('before_agent_start', async (event, ctx) => {
                api.logger.info('[TMR] before_agent_start fired');
                if (!event.prompt || event.prompt.length < 5)
                    return;
                try {
                    const result = (0, child_process_1.execSync)(`${pythonPath} ${path.join(pluginDir, 'src/plugin.py')} --inject "${event.prompt.replace(/"/g, '\\"')}"`, { encoding: 'utf-8', timeout: 5000 });
                    if (result && result.trim()) {
                        return { prependContext: result.trim() };
                    }
                }
                catch (err) {
                    api.logger.warn(`[TMR] Inject failed: ${err.message}`);
                }
            });
        }
        // AUTO-CAPTURE: Store conversation after agent ends  
        if (cfg.autoCapture !== false) {
            api.on('agent_end', async (event, ctx) => {
                api.logger.info('[TMR] agent_end hook fired!');
                if (!event.success) {
                    api.logger.info('[TMR] Skipping: event.success is false');
                    return;
                }
                if (!event.messages || event.messages.length === 0) {
                    api.logger.info('[TMR] Skipping: no messages');
                    return;
                }
                try {
                    const lastMsg = event.messages[event.messages.length - 1];
                    api.logger.info(`[TMR] Last message: ${JSON.stringify(lastMsg).substring(0, 100)}`);
                    // Simple file append
                    const date = new Date().toISOString().split('T')[0];
                    const filePath = path.join(rawDir, `${date}.md`);
                    const timestamp = new Date().toTimeString().split(' ')[0];
                    const role = lastMsg.role || 'unknown';
                    let content = '';
                    if (typeof lastMsg.content === 'string') {
                        content = lastMsg.content;
                    }
                    else if (Array.isArray(lastMsg.content)) {
                        for (const block of lastMsg.content) {
                            if (block && typeof block === 'object' && 'text' in block) {
                                content += (content ? '\n' : '') + block.text;
                            }
                        }
                    }
                    if (!content) {
                        api.logger.info('[TMR] Skipping: no text content');
                        return;
                    }
                    // Strip injected memory context
                    if (content.includes('<relevant-memories>')) {
                        content = content.replace(/<relevant-memories>[\s\S]*?<\/relevant-memories>\s*/g, '').trim();
                    }
                    if (!content) {
                        api.logger.info('[TMR] Skipping: empty after stripping context');
                        return;
                    }
                    const line = `[${timestamp}] ${role}: ${content.substring(0, 200)}\n`;
                    fs.appendFileSync(filePath, line);
                    api.logger.info(`[TMR] Successfully wrote to: ${filePath}`);
                }
                catch (err) {
                    api.logger.error(`[TMR] Capture error: ${err.message}`);
                }
            });
        }
        api.logger.info('[TMR] Initialization complete');
    },
    stop() {
        console.log('[TMR] Plugin stopped');
    }
};
exports.default = TMRPlugin;
