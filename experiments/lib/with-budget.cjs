/** Must be invoked through with-keys.cjs. Only this parent sees real keys. */
const { spawn } = require('node:child_process');
const { join } = require('node:path');
const { readFileSync } = require('node:fs');
const { randomUUID } = require('node:crypto');
const { gateway, Ledger } = require('./gateway.cjs');
const args = process.argv.slice(2);
const stage = args[args.indexOf('--stage') + 1];
const sep = args.indexOf('--run');
const cap = Number(process.env.BENCH_BUDGET_CNY);
if (!process.env.BENCH_BUDGET_CNY || cap !== 20 || sep < 0) throw Error('explicit BENCH_BUDGET_CNY=20 and --stage/--run required');
const config = JSON.parse(readFileSync(join(__dirname, 'prices.json'), 'utf8'));
if (config.status !== 'approved') throw Error('model/price confirmation required before paid requests');
const dir = join(process.env.LOCALAPPDATA, 'llm-bench', 'experiments', 'continuation-2026-09-30');
// 2026-09-30: user moved CNY 3.5 from reserve after the pilot (preflight +0.5, main +2, multi +1); total unchanged.
// Then +1 main from reserve after the full pilot projection (main 10, reserve 1.5).
const caps = { preflight: 1.5, index: 3, main: 10, multi: 3, cloud: 1, reserve: 1.5 };
if (!(stage in caps)) throw Error('unknown budget stage');
const ledger = new Ledger(join(dir, 'budget-ledger.json'), cap, caps);
const token = randomUUID();
const routes = {
  deepseek: { base: 'https://api.deepseek.com', key: process.env.BENCH_DEEPSEEK_KEY, models: config.deepseek.models },
  dashscope: { base: 'https://dashscope.aliyuncs.com/compatible-mode/v1', key: process.env.BENCH_DASHSCOPE_KEY, models: config.dashscope.models },
};
const server = gateway({ ledger, routes, stage, token });
server.listen(0, '127.0.0.1', () => {
  const base = `http://127.0.0.1:${server.address().port}`;
  const env = { ...process.env };
  for (const name of Object.keys(env)) if (/KEY|TOKEN|SECRET/i.test(name)) delete env[name];
  Object.assign(env, { BENCH_GATEWAY: base, BENCH_GATE_TOKEN: token, BENCH_LLM_BASE: base + '/deepseek', BENCH_LLM_MODEL: config.deepseek.model, BENCH_LLM_KEY: token, BENCH_DASHSCOPE_BASE: base + '/dashscope', BENCH_DASHSCOPE_KEY: token, BENCH_RUN_DIR: dir, OPENAI_API_KEY: token, OPENAI_BASE_URL: base + '/deepseek', OPENAI_AGENTS_DISABLE_TRACING: '1', HF_HUB_OFFLINE: '1', LITELLM_LOCAL_MODEL_COST_MAP: 'True', DO_NOT_TRACK: '1', BENCH_LEDGER: join(dir, 'budget-ledger.json') });
  const command = args.slice(sep + 1);
  const child = spawn(command[0], command.slice(1), { stdio: 'inherit', env, shell: process.platform === 'win32' });
  child.on('error', () => { server.close(); process.exitCode = 1; });
  child.on('exit', code => { server.close(); process.exitCode = code ?? 1; });
});
