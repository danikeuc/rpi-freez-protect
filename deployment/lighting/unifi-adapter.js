'use strict';
// Stateless normalization only. The controller owns deduplication and policy.
const ID = /^[A-Za-z0-9_.:-]{1,128}$/;
const TOKEN = /^[\x21-\x7e]{32,512}$/;
const UTC = /^(\d{4}-\d{2}-\d{2})T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|\+00:00)$/;
const PROFILE_KEYS = ['version','event_id_path','source_id_path','occurred_at_path',
    'event_type_path','allowed_event_types','occurred_at_format'];
function pathValid(path) {
    return Array.isArray(path) && path.length > 0 && path.length <= 8 &&
        path.every(k => typeof k === 'string' && /^[A-Za-z0-9_-]{1,64}$/.test(k) &&
            !['__proto__','constructor','prototype'].includes(k));
}
function field(body, path) {
    let value = body;
    for (const key of path) {
        if (!value || typeof value !== 'object' ||
            !Object.prototype.hasOwnProperty.call(value, key)) return undefined;
        value = value[key];
    }
    return value;
}
function reply(msg, code, payload) {
    msg.statusCode = code;
    msg.headers = {'content-type':'application/json','cache-control':'no-store'};
    msg.payload = payload;
    return msg;
}
function error(msg, code, cause) { return reply(msg, code, {error:cause}); }
function timestamp(value, format) {
    if (format === 'unix_ms') {
        if (!Number.isSafeInteger(value) || value < 0) return null;
        try { return new Date(value).toISOString(); } catch (_) { return null; }
    }
    if (typeof value !== 'string' || value.length < 20 || value.length > 40 ||
        !UTC.test(value)) return null;
    const ms = Date.parse(value);
    if (!Number.isFinite(ms) || new Date(ms).toISOString().slice(0,10) !== value.slice(0,10)) return null;
    return value;
}
async function handle(msg, config, deps) {
    let profile;
    try { profile = JSON.parse(config.profile); } catch (_) { return error(msg,503,'profile_unavailable'); }
    const sources = typeof config.allowedSources === 'string' ? config.allowedSources.split(',') : [];
    if (config.enabled !== 'commissioned' || !TOKEN.test(config.ingressToken || '') ||
        !TOKEN.test(config.cameraToken || '') || config.ingressToken === config.cameraToken ||
        !sources.length || !sources.every(s => ID.test(s)) || !profile || profile.version !== 1 ||
        Object.keys(profile).length !== PROFILE_KEYS.length ||
        !PROFILE_KEYS.every(k => Object.prototype.hasOwnProperty.call(profile,k)) ||
        !['utc','unix_ms'].includes(profile.occurred_at_format) ||
        !['event_id_path','source_id_path','occurred_at_path','event_type_path'].every(k => pathValid(profile[k])) ||
        !Array.isArray(profile.allowed_event_types) || !profile.allowed_event_types.length ||
        profile.allowed_event_types.length > 32 || !profile.allowed_event_types.every(t => ID.test(t))) {
        return error(msg,503,'profile_unavailable');
    }
    const req = msg.req || {};
    if (req.method !== 'POST') return error(msg,405,'method_rejected');
    if (typeof req.url !== 'string' || req.url.includes('?')) return error(msg,401,'credentials_rejected');
    const headers = req.headers || {};
    const auth = headers.authorization;
    const expected = 'Bearer ' + config.ingressToken;
    if (typeof auth !== 'string' || !/^[\x21-\x7e ]+$/.test(auth) || auth.length !== expected.length ||
        !deps.crypto.timingSafeEqual(Buffer.from(auth),Buffer.from(expected))) return error(msg,401,'credentials_rejected');
    if (!/^application\/json(?:\s*;\s*charset=utf-8)?$/i.test(headers['content-type'] || '')) return error(msg,415,'content_type_rejected');
    let body = msg.payload;
    try {
        const raw = Buffer.isBuffer(body) ? body.toString('utf8') : typeof body === 'string' ? body : JSON.stringify(body);
        if (typeof raw !== 'string') return error(msg,422,'event_rejected');
        if (Buffer.byteLength(raw) > 4096 || Number(headers['content-length'] || 0) > 4096) return error(msg,413,'body_too_large');
        if (typeof body === 'string' || Buffer.isBuffer(body)) body = JSON.parse(raw);
    } catch (_) { return error(msg,422,'event_rejected'); }
    if (!body || typeof body !== 'object' || Array.isArray(body)) return error(msg,422,'event_rejected');
    const event_id = field(body,profile.event_id_path), source_id = field(body,profile.source_id_path);
    const occurred_at = timestamp(field(body,profile.occurred_at_path),profile.occurred_at_format);
    const type = field(body,profile.event_type_path);
    if (typeof event_id !== 'string' || !ID.test(event_id) ||
        typeof source_id !== 'string' || !ID.test(source_id) || !occurred_at ||
        typeof type !== 'string' || !profile.allowed_event_types.includes(type)) return error(msg,422,'event_rejected');
    if (!sources.includes(source_id)) return error(msg,403,'source_rejected');
    const age = (deps.now ? deps.now() : Date.now()) - Date.parse(occurred_at);
    if (age > 60000 || age < -5000) return error(msg,422,'event_rejected');
    const payload = JSON.stringify({event_id,source_id,occurred_at});
    // Caller input can never choose upstream method/host/path/headers.
    return new Promise(resolve => {
        let settled = false, upstream, timer;
        const cancel = () => finish(503,{error:'controller_unavailable'});
        function finish(code, result) {
            if (settled) return;
            settled = true;
            clearTimeout(timer);
            if (deps.pending) deps.pending.delete(cancel);
            if (upstream) upstream.destroy();
            resolve(reply(msg,code,result));
        }
        timer = setTimeout(cancel, Math.min(deps.timeoutMs || 1500,1500));
        if (deps.pending) deps.pending.add(cancel);
        try {
            upstream = deps.http.request({hostname:'127.0.0.1',port:8002,
                path:'/api/v1/lights/events/unifi',method:'POST',agent:false,
                headers:{Authorization:'Bearer '+config.cameraToken,
                    'Content-Type':'application/json','Content-Length':Buffer.byteLength(payload)}}, response => {
                let size = 0, chunks = [];
                response.on('error',cancel);
                response.on('aborted',cancel);
                response.on('data',chunk => {
                    size += chunk.length;
                    if (size > 8192) { cancel(); response.destroy(); return; }
                    chunks.push(chunk);
                });
                response.on('end',() => {
                    if (settled) return;
                    if (response.statusCode !== 200) {
                        const code = [401,403,409,413,422,429,503].includes(response.statusCode) ? response.statusCode : 503;
                        finish(code,{error:code === 503 ? 'controller_unavailable' : 'controller_rejected'});
                        return;
                    }
                    try {
                        const result = JSON.parse(Buffer.concat(chunks).toString('utf8'));
                        if (typeof result.accepted !== 'boolean' || typeof result.duplicate !== 'boolean') { cancel(); return; }
                        // Never return raw controller errors/payload, credentials or headers.
                        finish(200,{accepted:result.accepted,duplicate:result.duplicate});
                    } catch (_) { cancel(); }
                });
            });
            upstream.on('error',cancel);
            upstream.end(payload);
        } catch (_) { cancel(); }
    });
}
module.exports = {handle};
